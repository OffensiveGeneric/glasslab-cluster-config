import json
from pathlib import Path

import pandas as pd

from app.config import Settings
from app.runner import run_experiment


FIXTURE_ROOT = Path(__file__).parent / 'fixtures' / 'titanic'


def test_runner_baseline_generates_expected_artifacts(tmp_path) -> None:
    settings = Settings(
        experiment_id='runner-test',
        trace_id='trace-test',
        dataset_root=str(FIXTURE_ROOT),
        artifacts_root=str(tmp_path),
        mlflow_enabled=False,
        spec_json=json.dumps(
            {
                'pipeline': 'titanic_baseline',
                'dataset': 'titanic',
                'models': ['logistic_regression', 'random_forest'],
                'feature_profile': 'basic',
                'resource_profile': 'cpu-small',
                'compare_to': 'none',
                'produce_submission': True,
            }
        ),
    )

    result = run_experiment(settings)
    artifact_dir = tmp_path / 'runner-test'

    assert result['best_model'] in {'logistic_regression', 'random_forest'}
    assert (artifact_dir / 'metrics.json').exists()
    assert (artifact_dir / 'model_comparison.json').exists()
    assert (artifact_dir / 'feature_summary.json').exists()
    assert (artifact_dir / 'result_payload.json').exists()
    assert (artifact_dir / 'submission.csv').exists()

    submission = pd.read_csv(artifact_dir / 'submission.csv')
    assert list(submission.columns) == ['PassengerId', 'Survived']
    assert set(submission['Survived'].unique()).issubset({0, 1})
