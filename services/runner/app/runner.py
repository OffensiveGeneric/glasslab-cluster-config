from __future__ import annotations

import json
import logging
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


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format='%(asctime)s %(levelname)s %(name)s %(message)s')


def run_experiment(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    spec = settings.parsed_spec
    artifact_dir = settings.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)

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

    feature_profile = spec['feature_profile']
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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
