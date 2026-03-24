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


def test_create_and_fetch_interpretation_from_latest_intake() -> None:
    client = build_client()

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': [
                'The paper compares a baseline on Titanic.',
                'Focus on the reported metrics and dataset assumptions.',
            ],
        },
    )
    assert create_intake.status_code == 201
    intake_id = create_intake.json()['intake_id']

    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201
    payload = create_interpretation.json()
    interpretation_id = payload['interpretation_id']
    assert payload['intake_id'] == intake_id
    assert 'generic-tabular-benchmark' in payload['candidate_workflow_families']
    assert 'titanic' in payload['dataset_hints']
    assert payload['status'] in {'ready_for_assessment', 'needs_review'}

    latest = client.get('/interpretations/latest')
    assert latest.status_code == 200
    assert latest.json()['interpretation_id'] == interpretation_id

    fetched = client.get(f'/interpretations/{interpretation_id}')
    assert fetched.status_code == 200
    assert fetched.json()['extracted_claims'][0].startswith('The paper compares')


def test_create_interpretation_requires_intake() -> None:
    client = build_client()

    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 404
    assert create_interpretation.json()['detail'] == 'intake not found'


def test_create_and_fetch_replicability_assessment_from_latest_interpretation() -> None:
    client = build_client()

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': [
                'The paper compares a baseline on Titanic.',
                'Focus on the reported metrics and dataset assumptions.',
            ],
        },
    )
    assert create_intake.status_code == 201

    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201
    interpretation_id = create_interpretation.json()['interpretation_id']

    create_assessment = client.post('/replicability-assessments/from-latest-interpretation')
    assert create_assessment.status_code == 201
    payload = create_assessment.json()
    assessment_id = payload['assessment_id']
    assert payload['interpretation_id'] == interpretation_id
    assert payload['recommendation'] == 'proceed'
    assert payload['recommended_workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status'] == 'ready_for_design'

    latest = client.get('/replicability-assessments/latest')
    assert latest.status_code == 200
    assert latest.json()['assessment_id'] == assessment_id

    fetched = client.get(f'/replicability-assessments/{assessment_id}')
    assert fetched.status_code == 200
    assert fetched.json()['approval_tier'] == 'tier-2-approved-execution'


def test_create_replicability_assessment_requires_interpretation() -> None:
    client = build_client()

    create_assessment = client.post('/replicability-assessments/from-latest-interpretation')
    assert create_assessment.status_code == 404
    assert create_assessment.json()['detail'] == 'interpretation not found'


def test_create_and_fetch_design_draft_from_latest_titanic_intake() -> None:
    client = build_client()

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Benchmark the approved models on the Titanic dataset and validate the baseline results.',
            'notes': ['Use the standard Titanic train/test splits.'],
        },
    )
    assert create_intake.status_code == 201
    intake_id = create_intake.json()['intake_id']

    create_design = client.post('/design-drafts/from-latest-intake')
    assert create_design.status_code == 201
    payload = create_design.json()
    design_id = payload['design_id']
    assert payload['intake_id'] == intake_id
    assert payload['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status'] == 'ready_for_run'
    assert payload['declared_inputs']['dataset_name'] == 'titanic'
    assert payload['unresolved_inputs'] == []

    latest = client.get('/design-drafts/latest')
    assert latest.status_code == 200
    assert latest.json()['design_id'] == design_id

    fetched = client.get(f'/design-drafts/{design_id}')
    assert fetched.status_code == 200
    assert fetched.json()['candidate_models'] == ['logistic_regression', 'random_forest']


def test_create_design_draft_from_latest_assessment() -> None:
    client = build_client()

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': [
                'The paper compares a baseline on Titanic.',
                'Focus on the reported metrics and dataset assumptions.',
            ],
        },
    )
    assert create_intake.status_code == 201
    intake_id = create_intake.json()['intake_id']

    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201

    create_assessment = client.post('/replicability-assessments/from-latest-interpretation')
    assert create_assessment.status_code == 201
    assessment_id = create_assessment.json()['assessment_id']

    create_design = client.post('/design-drafts/from-latest-assessment')
    assert create_design.status_code == 201
    payload = create_design.json()
    assert payload['intake_id'] == intake_id
    assert payload['source_assessment_id'] == assessment_id
    assert payload['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status'] == 'ready_for_run'


def test_create_design_draft_from_latest_assessment_requires_assessment() -> None:
    client = build_client()

    create_design = client.post('/design-drafts/from-latest-assessment')
    assert create_design.status_code == 404
    assert create_design.json()['detail'] == 'replicability assessment not found'


def test_create_design_draft_prefers_benchmark_for_titanic_paper_intake() -> None:
    client = build_client()

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Start a bounded paper-to-validation intake for the approved Titanic benchmark path.',
            'source_refs': ['https://www.kaggle.com/competitions/titanic'],
            'source_type': 'paper-link',
            'notes': [
                'Use the approved Titanic dataset path for the first intake-to-design validation.',
                'Keep the workflow family inside the approved Glasslab registry.',
            ],
        },
    )
    assert create_intake.status_code == 201

    create_design = client.post('/design-drafts/from-latest-intake')
    assert create_design.status_code == 201
    payload = create_design.json()
    assert payload['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status'] == 'ready_for_run'
    assert payload['unresolved_inputs'] == []


def test_create_design_draft_requires_intake() -> None:
    client = build_client()

    create_design = client.post('/design-drafts/from-latest-intake')
    assert create_design.status_code == 404
    assert create_design.json()['detail'] == 'intake not found'


def test_create_run_from_latest_ready_design_draft() -> None:
    client = build_client()

    intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Benchmark the approved models on Titanic and create a validation run.',
            'notes': ['Use the standard Titanic train/test splits.'],
        },
    )
    assert intake.status_code == 201

    design = client.post('/design-drafts/from-latest-intake')
    assert design.status_code == 201
    design_payload = design.json()

    run = client.post('/runs/from-latest-design-draft')
    assert run.status_code == 201
    payload = run.json()
    assert payload['source_design_id'] == design_payload['design_id']
    assert payload['source_intake_id'] == design_payload['intake_id']
    assert payload['run_purpose'] == 'validation'
    assert payload['manifest']['inputs']['dataset_name'] == 'titanic'


def test_create_run_from_latest_design_draft_blocks_non_ready_design() -> None:
    client = build_client()

    intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Turn this paper into a bounded experiment design based on the linked notes.',
            'source_refs': ['https://example.org/paper-notes'],
            'notes': ['Focus on the method section and reported metrics.'],
        },
    )
    assert intake.status_code == 201

    design = client.post('/design-drafts/from-latest-intake')
    assert design.status_code == 201
    assert design.json()['status'] == 'needs_review'

    run = client.post('/runs/from-latest-design-draft')
    assert run.status_code == 409
    assert run.json()['detail'] == 'design draft is not ready_for_run'


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


def test_get_run_reflects_disk_artifacts_and_status(tmp_path) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        artifacts_mount_path=str(tmp_path),
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

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
    run_id = response.json()['run_id']

    run_dir = tmp_path / run_id
    (run_dir / 'logs').mkdir(parents=True)
    (run_dir / 'status.json').write_text(
        '{"run_id":"%s","status":"succeeded","updated_at":"2026-03-23T20:34:44Z","detail":"done"}' % run_id
    )
    (run_dir / 'artifacts_index.json').write_text(
        '{"run_id":"%s","artifacts":[{"name":"status.json","path":"artifacts/%s/status.json","media_type":"application/json","required":true}]}'
        % (run_id, run_id)
    )
    (run_dir / 'logs' / 'runner.log').write_text('2026-03-23 20:34:44,470 INFO glasslab.runner completed Titanic baseline run\n')

    run = client.get(f'/runs/{run_id}')
    assert run.status_code == 200
    assert run.json()['status']['status'] == 'succeeded'

    artifacts = client.get(f'/runs/{run_id}/artifacts')
    assert artifacts.status_code == 200
    assert artifacts.json()['artifacts']['artifacts'][0]['name'] == 'status.json'

    logs = client.get(f'/runs/{run_id}/logs')
    assert logs.status_code == 200
    assert logs.json()['logs'][0]['message'] == 'completed Titanic baseline run'
