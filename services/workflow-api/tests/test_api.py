from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.persistence import InMemoryRunStore
from app.registry import WorkflowRegistry

REPO_ROOT = Path(__file__).resolve().parents[3]


def build_client() -> TestClient:
    settings = Settings(registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'))
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    return TestClient(create_app(settings=settings, registry=registry, store=store))


def test_healthz_and_workflow_families() -> None:
    client = build_client()

    health = client.get('/healthz')
    assert health.status_code == 200
    assert health.json()['workflow_count'] == 3

    families = client.get('/workflow-families')
    assert families.status_code == 200
    payload = families.json()
    assert {entry['workflow_id'] for entry in payload} == {
        'generic-tabular-benchmark',
        'literature-to-experiment',
        'replication-lite',
    }


def test_create_run_success() -> None:
    client = build_client()

    response = client.post(
        '/runs',
        json={
            'workflow_id': 'generic-tabular-benchmark',
            'objective': 'Benchmark approved models on Titanic.',
            'inputs': {
                'dataset_name': 'titanic',
                'train_uri': 's3://datasets/titanic/train.csv',
                'test_uri': 's3://datasets/titanic/test.csv',
                'target_column': 'Survived',
            },
            'models': ['logistic_regression', 'random_forest'],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    run_id = payload['run_id']
    assert payload['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status']['status'] == 'accepted'
    assert payload['manifest']['expected_artifacts']['required'][0] == 'run_manifest.json'

    run = client.get(f'/runs/{run_id}')
    assert run.status_code == 200

    artifacts = client.get(f'/runs/{run_id}/artifacts')
    assert artifacts.status_code == 200
    assert any(item['name'] == 'report.md' for item in artifacts.json()['artifacts']['artifacts'])

    logs = client.get(f'/runs/{run_id}/logs')
    assert logs.status_code == 200
    assert logs.json()['logs'][0]['message'] == 'run accepted'
