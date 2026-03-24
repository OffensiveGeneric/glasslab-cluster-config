from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .config import Settings
from .features import build_preprocessor, engineer_features
from .mlflow_client import MlflowRunLogger


LOGGER = logging.getLogger('glasslab.runner')
MEDIA_TYPES = {
    '.json': 'application/json',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.log': 'text/plain',
    '.txt': 'text/plain',
}
REQUIRED_ARTIFACTS = {
    'run_manifest.json',
    'config.json',
    'metrics.json',
    'artifacts_index.json',
    'report.md',
    'status.json',
    'logs/',
    'logs/runner.log',
}


def run_literature_to_experiment(settings: Settings, spec: dict, artifact_dir: Path) -> dict:
    paper_id = str(spec.get('paper_id', '')).strip()
    source_notes = str(spec.get('source_notes', '')).strip()
    dataset_uri = str(spec.get('dataset_uri', '')).strip()
    requested_models = [str(item).strip() for item in spec.get('models', []) if str(item).strip()]
    if not paper_id:
        raise ValueError('literature_to_experiment requires paper_id')
    if not source_notes:
        raise ValueError('literature_to_experiment requires source_notes')
    if not dataset_uri:
        raise ValueError('literature_to_experiment requires dataset_uri')
    if not requested_models:
        raise ValueError('literature_to_experiment requires at least one requested model')

    selected_model = requested_models[0]
    method_spec = {
        'paper_id': paper_id,
        'dataset_uri': dataset_uri,
        'selected_model': selected_model,
        'requested_models': requested_models,
        'resource_profile': spec.get('resource_profile'),
        'execution_outline': [
            'normalize reviewed paper notes',
            'bind the resolved dataset URI',
            f'prepare a bounded experiment draft using {selected_model}',
            'emit deterministic artifacts for backend evaluation and reporting',
        ],
    }
    design_notes = [
        f'# Literature To Experiment Draft {settings.experiment_id}',
        '',
        f'- paper_id: `{paper_id}`',
        f'- dataset_uri: `{dataset_uri}`',
        f'- selected_model: `{selected_model}`',
        '',
        '## Source Notes',
        '',
        source_notes,
        '',
        '## Backend Summary',
        '',
        'This run produced a deterministic method specification from the reviewed literature intake.',
    ]
    metrics_payload = {
        'metric_name': 'spec_readiness',
        'best_model': selected_model,
        'best_metric': 1.0,
        'models': {
            selected_model: {
                'score': 1.0,
                'score_name': 'spec_readiness',
                'paper_id': paper_id,
                'dataset_uri_present': True,
            }
        },
        'paper_id': paper_id,
        'dataset_uri': dataset_uri,
    }
    result_payload = {
        'experiment_id': settings.experiment_id,
        'trace_id': settings.trace_id,
        'pipeline': spec['pipeline'],
        'dataset': dataset_uri,
        'paper_id': paper_id,
        'selected_model': selected_model,
        'metric_name': 'spec_readiness',
        'best_metric': 1.0,
        'artifact_dir': str(artifact_dir),
    }

    write_json(artifact_dir / 'metrics.json', metrics_payload)
    write_json(artifact_dir / 'method_spec.json', method_spec)
    write_json(artifact_dir / 'result_payload.json', result_payload)
    (artifact_dir / 'design_notes.md').write_text('\n'.join(design_notes) + '\n')

    LOGGER.info(
        'completed literature-to-experiment draft run',
        extra={'experiment_id': settings.experiment_id, 'paper_id': paper_id},
    )
    return result_payload


def configure_logging(level: str, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level.upper())

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def run_experiment(settings: Settings | None = None) -> dict:
    settings = settings or Settings()

    spec = settings.parsed_spec
    artifact_dir = settings.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(settings.log_level, artifact_dir / 'logs' / 'runner.log')

    feature_profile = spec['feature_profile']
    if spec['pipeline'] == 'literature_to_experiment':
        return run_literature_to_experiment(settings, spec, artifact_dir)

    dataset_root = Path(settings.dataset_root)
    train_path = dataset_root / 'train.csv'
    test_path = dataset_root / 'test.csv'
    if not train_path.exists():
        raise FileNotFoundError(f'missing training data at {train_path}')

    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path) if test_path.exists() else None
    if 'Survived' not in train_df.columns:
        raise ValueError('train.csv must contain a Survived column')

    y = train_df['Survived'].astype(int)
    X = train_df.drop(columns=['Survived'])

    X_train, X_valid, y_train, y_valid = train_test_split(
        X,
        y,
        test_size=settings.validation_size,
        random_state=settings.random_state,
        stratify=y,
    )

    mlflow_logger = MlflowRunLogger(
        enabled=settings.mlflow_enabled,
        tracking_uri=settings.mlflow_tracking_uri,
        experiment_name=settings.mlflow_experiment_name,
    )

    with mlflow_logger.start_run(run_name=settings.experiment_id):
        mlflow_logger.log_params(
            {
                'pipeline': spec['pipeline'],
                'dataset': spec['dataset'],
                'feature_profile': feature_profile,
                'models': ','.join(spec['models']),
                'compare_to': spec['compare_to'],
                'produce_submission': str(spec['produce_submission']).lower(),
            }
        )

        model_comparison: dict[str, dict] = {}
        for model_name in spec['models']:
            pipeline, feature_summary = build_model_pipeline(
                model_name=model_name,
                feature_profile=feature_profile,
                random_state=settings.random_state,
            )
            pipeline.fit(engineer_features(X_train, feature_profile), y_train)
            predictions = pipeline.predict(engineer_features(X_valid, feature_profile))
            accuracy = float(accuracy_score(y_valid, predictions))
            model_comparison[model_name] = {
                'accuracy': accuracy,
                'validation_rows': int(len(y_valid)),
                'model_name': model_name,
            }
            mlflow_logger.log_metric(f'{model_name}_accuracy', accuracy)

        best_model_name = max(model_comparison, key=lambda name: model_comparison[name]['accuracy'])
        best_metric = model_comparison[best_model_name]['accuracy']
        best_pipeline, feature_summary = build_model_pipeline(
            model_name=best_model_name,
            feature_profile=feature_profile,
            random_state=settings.random_state,
        )
        best_pipeline.fit(engineer_features(X, feature_profile), y)

        submission_created = False
        submission_path = None
        if test_df is not None and spec.get('produce_submission', False):
            submission = pd.DataFrame(
                {
                    'PassengerId': test_df['PassengerId'].astype(int),
                    'Survived': best_pipeline.predict(engineer_features(test_df, feature_profile)).astype(int),
                }
            )
            submission_path = artifact_dir / 'submission.csv'
            submission.to_csv(submission_path, index=False)
            submission_created = True
            mlflow_logger.log_artifact(str(submission_path))

        metrics_payload = {
            'metric_name': 'accuracy',
            'best_model': best_model_name,
            'best_metric': best_metric,
            'models': model_comparison,
        }
        model_comparison_payload = {
            'winner': best_model_name,
            'metric_name': 'accuracy',
            'models': model_comparison,
        }
        result_payload = {
            'experiment_id': settings.experiment_id,
            'trace_id': settings.trace_id,
            'pipeline': spec['pipeline'],
            'dataset': spec['dataset'],
            'feature_profile': feature_profile,
            'models_ran': spec['models'],
            'best_model': best_model_name,
            'metric_name': 'accuracy',
            'best_metric': best_metric,
            'submission_created': submission_created,
            'submission_path': str(submission_path) if submission_path else None,
            'artifact_dir': str(artifact_dir),
        }

        write_json(artifact_dir / 'metrics.json', metrics_payload)
        write_json(artifact_dir / 'model_comparison.json', model_comparison_payload)
        write_json(artifact_dir / 'feature_summary.json', feature_summary)
        write_json(artifact_dir / 'result_payload.json', result_payload)

        for artifact_name in ['metrics.json', 'model_comparison.json', 'feature_summary.json', 'result_payload.json']:
            mlflow_logger.log_artifact(str(artifact_dir / artifact_name))

        LOGGER.info('completed Titanic baseline run', extra={'experiment_id': settings.experiment_id, 'best_model': best_model_name})
        return result_payload


def build_artifacts_index(settings: Settings, status: str) -> dict:
    artifact_dir = settings.artifact_dir
    entries: list[dict] = []
    for path in sorted(artifact_dir.rglob('*')):
        if path == artifact_dir:
            continue
        relative = path.relative_to(artifact_dir).as_posix()
        if path.is_dir():
            entries.append(
                {
                    'name': f'{relative}/',
                    'path': f'artifacts/{settings.experiment_id}/{relative}/',
                    'media_type': 'inode/directory',
                    'required': f'{relative}/' in REQUIRED_ARTIFACTS,
                    'description': 'Runner-created directory',
                }
            )
            continue
        entries.append(
            {
                'name': relative,
                'path': f'artifacts/{settings.experiment_id}/{relative}',
                'media_type': MEDIA_TYPES.get(path.suffix.lower(), 'application/octet-stream'),
                'required': relative in REQUIRED_ARTIFACTS,
                'description': f'Runner-generated artifact ({status})',
                'size_bytes': path.stat().st_size,
            }
        )
    return {'run_id': settings.experiment_id, 'artifacts': entries}


def write_supporting_artifacts(settings: Settings, result_payload: dict, status: str, error: str | None = None) -> None:
    artifact_dir = settings.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / 'logs').mkdir(parents=True, exist_ok=True)

    config_payload = {
        'experiment_id': settings.experiment_id,
        'trace_id': settings.trace_id,
        'dataset_root': settings.dataset_root,
        'artifacts_root': settings.artifacts_root,
        'spec': settings.parsed_spec,
    }
    write_json(artifact_dir / 'config.json', config_payload)

    if settings.manifest_json:
        try:
            write_json(artifact_dir / 'run_manifest.json', json.loads(settings.manifest_json))
        except json.JSONDecodeError:
            write_json(
                artifact_dir / 'run_manifest.json',
                {'run_id': settings.experiment_id, 'raw_manifest_json': settings.manifest_json},
            )

    status_payload = {
        'run_id': settings.experiment_id,
        'status': status,
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'detail': error or f'Runner finished with status={status}.',
    }
    write_json(artifact_dir / 'status.json', status_payload)

    report_lines = [
        f'# Run {settings.experiment_id}',
        '',
        f'- status: `{status}`',
        f'- trace_id: `{settings.trace_id}`',
        f'- dataset: `{result_payload.get("dataset", settings.parsed_spec.get("dataset", "unknown"))}`',
        f'- pipeline: `{result_payload.get("pipeline", settings.parsed_spec.get("pipeline", "unknown"))}`',
    ]
    if 'best_model' in result_payload:
        report_lines.append(f'- best_model: `{result_payload["best_model"]}`')
    if 'best_metric' in result_payload:
        report_lines.append(f'- best_metric: `{result_payload["best_metric"]}`')
    if error:
        report_lines.extend(['', '## Error', '', error])
    (artifact_dir / 'report.md').write_text('\n'.join(report_lines) + '\n')

    write_json(artifact_dir / 'artifacts_index.json', build_artifacts_index(settings, status=status))


def build_model_pipeline(model_name: str, feature_profile: str, random_state: int) -> tuple[Pipeline, dict]:
    preprocessor, feature_summary = build_preprocessor(feature_profile)

    if model_name == 'logistic_regression':
        estimator = LogisticRegression(max_iter=1000, solver='liblinear', random_state=random_state)
    elif model_name == 'random_forest':
        estimator = RandomForestClassifier(
            n_estimators=300,
            random_state=random_state,
            min_samples_leaf=1,
        )
    elif model_name == 'xgboost_optional':
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise RuntimeError('xgboost_optional requested but xgboost is not installed') from exc
        estimator = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective='binary:logistic',
            eval_metric='logloss',
            random_state=random_state,
        )
    else:
        raise ValueError(f'unsupported model_name: {model_name}')

    pipeline = Pipeline(
        steps=[
            ('preprocessor', preprocessor),
            ('model', estimator),
        ]
    )
    return pipeline, feature_summary


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
