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


def test_create_and_fetch_latest_intake() -> None:
    client = build_client()

    create = client.post(
        '/intakes',
        json={
            'raw_request': 'Take this paper note set and turn it into a bounded validation experiment on a tabular dataset.',
            'source_refs': ['arxiv:2401.12345', 'https://example.org/paper-notes'],
            'notes': ['Focus on the reported baseline and evaluation method.'],
        },
    )

    assert create.status_code == 201
    payload = create.json()
    intake_id = payload['intake_id']
    assert payload['status'] == 'ready_for_design'
    assert payload['source_type'] == 'paper-link'
    assert 'literature-to-experiment' in payload['workflow_family_candidates']
    assert 'generic-tabular-benchmark' in payload['workflow_family_candidates']

    latest = client.get('/intakes/latest')
    assert latest.status_code == 200
    assert latest.json()['intake_id'] == intake_id

    fetched = client.get(f'/intakes/{intake_id}')
    assert fetched.status_code == 200
    assert fetched.json()['normalized_summary'].startswith('Take this paper note set')


def test_get_latest_intake_missing() -> None:
    client = build_client()

    latest = client.get('/intakes/latest')
    assert latest.status_code == 404
    assert latest.json()['detail'] == 'intake not found'


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
