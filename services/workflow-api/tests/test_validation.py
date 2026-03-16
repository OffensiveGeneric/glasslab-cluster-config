from pathlib import Path

from app.registry import WorkflowRegistry
from app.schemas import RunCreateRequest
from app.validation import validate_run_request

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_validation_rejects_missing_inputs_and_bad_resource_profile() -> None:
    registry = WorkflowRegistry(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions')
    workflow = registry.get_workflow('generic-tabular-benchmark')
    assert workflow is not None

    request = RunCreateRequest(
        workflow_id='generic-tabular-benchmark',
        objective='Benchmark approved models on Titanic.',
        inputs={
            'dataset_name': 'titanic',
            'train_uri': 's3://datasets/titanic/train.csv',
        },
        models=['logistic_regression'],
        resource_profile='gpu-small',
    )

    issues = validate_run_request(request, workflow)
    fields = {issue.field for issue in issues}
    assert 'inputs.test_uri' in fields
    assert 'inputs.target_column' in fields
    assert 'resource_profile' in fields


def test_validation_rejects_disallowed_models() -> None:
    registry = WorkflowRegistry(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions')
    workflow = registry.get_workflow('generic-tabular-benchmark')
    assert workflow is not None

    request = RunCreateRequest(
        workflow_id='generic-tabular-benchmark',
        objective='Benchmark approved models on Titanic.',
        inputs={
            'dataset_name': 'titanic',
            'train_uri': 's3://datasets/titanic/train.csv',
            'test_uri': 's3://datasets/titanic/test.csv',
            'target_column': 'Survived',
        },
        models=['made_up_model'],
    )

    issues = validate_run_request(request, workflow)
    assert len(issues) == 1
    assert issues[0].field == 'models'
    assert 'made_up_model' in issues[0].message
