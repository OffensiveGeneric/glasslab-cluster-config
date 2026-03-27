import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

for module_name in list(sys.modules):
    if module_name == 'app' or module_name.startswith('app.'):
        del sys.modules[module_name]

from app.config import Settings
import app.main as main_module
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
    assert health.json()['workflow_count'] == 4
    assert health.json()['store_backend'] == 'memory'

    families = client.get('/workflow-families')
    assert families.status_code == 200
    payload = families.json()
    assert {entry['workflow_id'] for entry in payload} == {
        'gpu-neural-net-experiment',
        'generic-tabular-benchmark',
        'literature-to-experiment',
        'replication-lite',
    }
    by_id = {entry['workflow_id']: entry for entry in payload}
    assert by_id['gpu-neural-net-experiment']['execution_status'] == 'ready'
    assert by_id['gpu-neural-net-experiment']['submission_backend'] == 'kubernetes'
    assert by_id['gpu-neural-net-experiment']['resource_profile'] == 'gpu-small'
    assert by_id['generic-tabular-benchmark']['execution_status'] == 'ready'
    assert by_id['generic-tabular-benchmark']['submission_backend'] == 'kubernetes'
    assert by_id['replication-lite']['execution_status'] == 'declared_only'
    assert by_id['replication-lite']['submission_backend'] == 'unimplemented'


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


def test_json_store_persists_intake_across_restart(tmp_path) -> None:
    state_path = tmp_path / 'run-store.json'
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        store_backend='json',
        store_json_path=str(state_path),
    )
    registry = WorkflowRegistry(settings.registry_dir)

    first_client = TestClient(create_app(settings=settings, registry=registry))
    create = first_client.post(
        '/intakes',
        json={
            'raw_request': 'Turn this literature note into a bounded experiment.',
            'source_refs': ['https://example.org/paper-notes'],
            'notes': ['Persist this intake.'],
        },
    )

    assert create.status_code == 201
    intake_id = create.json()['intake_id']
    assert state_path.exists()

    second_client = TestClient(create_app(settings=settings, registry=registry))
    latest = second_client.get('/intakes/latest')
    assert latest.status_code == 200
    assert latest.json()['intake_id'] == intake_id


def test_create_app_rejects_implicit_memory_store_when_disallowed() -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        store_backend='memory',
        allow_inmemory_store=False,
    )
    registry = WorkflowRegistry(settings.registry_dir)

    try:
        create_app(settings=settings, registry=registry)
    except RuntimeError as exc:
        assert 'allow_inmemory_store=false' in str(exc)
    else:
        raise AssertionError('expected create_app to reject implicit in-memory store')


def test_create_intake_uses_agent_when_enabled(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        intake_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    def fake_call_intake_agent(request, settings, registry):
        return main_module.build_intake_record_from_agent_draft(
            {
                'source_type': 'paper-link',
                'source_refs': ['https://example.org/agent-paper'],
                'raw_request': request.raw_request,
                'normalized_summary': 'agent-normalized intake summary',
                'workflow_family_candidates': ['literature-to-experiment'],
                'notes': ['Agent normalized note'],
                'submitted_by': 'agent-operator',
            }
        )

    monkeypatch.setattr(main_module, 'call_intake_agent', fake_call_intake_agent)

    create = client.post(
        '/intakes',
        json={
            'raw_request': 'Take this paper note set and turn it into a bounded validation experiment on a tabular dataset.',
            'source_refs': ['https://example.org/paper-notes'],
            'notes': ['Focus on the reported baseline and evaluation method.'],
        },
    )

    assert create.status_code == 201
    payload = create.json()
    assert payload['normalized_summary'] == 'agent-normalized intake summary'
    assert payload['workflow_family_candidates'] == ['literature-to-experiment']
    assert payload['submitted_by'] == 'agent-operator'


def test_create_intake_falls_back_when_agent_returns_none(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        intake_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    monkeypatch.setattr(main_module, 'call_intake_agent', lambda request, settings, registry: None)

    create = client.post(
        '/intakes',
        json={
            'raw_request': 'Take this paper note set and turn it into a bounded validation experiment on a tabular dataset.',
            'source_refs': ['https://example.org/paper-notes'],
            'notes': ['Focus on the reported baseline and evaluation method.'],
        },
    )

    assert create.status_code == 201
    payload = create.json()
    assert payload['normalized_summary'].startswith('Take this paper note set')
    assert 'generic-tabular-benchmark' in payload['workflow_family_candidates']


def test_create_intake_uses_ranker_when_scores_are_strong(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        ranker_enabled=True,
        ranker_min_top_score=0.75,
        ranker_min_score_gap=0.10,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    def fake_urlopen(request_obj, timeout):
        return FakeResponse(
            {
                'request_id': 'ignored',
                'ranked_candidates': [
                    {
                        'workflow_id': 'generic-tabular-benchmark',
                        'score': 0.92,
                        'reason': 'strong tabular benchmark signal',
                    },
                    {
                        'workflow_id': 'literature-to-experiment',
                        'score': 0.61,
                        'reason': 'paper-oriented fallback',
                    },
                ],
                'ranking_basis': 'test fixture',
            }
        )

    monkeypatch.setattr(main_module.urllib_request, 'urlopen', fake_urlopen)

    create = client.post(
        '/intakes',
        json={
            'raw_request': 'Take this paper note set and turn it into a bounded validation experiment on a tabular dataset.',
            'source_refs': ['https://example.org/paper-notes'],
            'notes': ['Focus on the reported baseline and evaluation method.'],
        },
    )

    assert create.status_code == 201
    payload = create.json()
    assert payload['workflow_family_candidates'] == [
        'generic-tabular-benchmark',
        'literature-to-experiment',
    ]


def test_create_intake_ignores_ranker_when_scores_are_ambiguous(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        ranker_enabled=True,
        ranker_min_top_score=0.75,
        ranker_min_score_gap=0.10,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    def fake_urlopen(request_obj, timeout):
        return FakeResponse(
            {
                'request_id': 'ignored',
                'ranked_candidates': [
                    {
                        'workflow_id': 'generic-tabular-benchmark',
                        'score': 0.78,
                        'reason': 'slightly preferred',
                    },
                    {
                        'workflow_id': 'literature-to-experiment',
                        'score': 0.74,
                        'reason': 'close alternative',
                    },
                ],
                'ranking_basis': 'test fixture',
            }
        )

    monkeypatch.setattr(main_module.urllib_request, 'urlopen', fake_urlopen)

    create = client.post(
        '/intakes',
        json={
            'raw_request': 'Take this paper note set and turn it into a bounded validation experiment on a tabular dataset.',
            'source_refs': ['https://example.org/paper-notes'],
            'notes': ['Focus on the reported baseline and evaluation method.'],
        },
    )

    assert create.status_code == 201
    payload = create.json()
    assert payload['workflow_family_candidates'] == [
        'literature-to-experiment',
        'generic-tabular-benchmark',
    ]


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
    assert payload['literature_state_summary'].startswith('Current bounded literature view:')
    assert payload['bounded_experiment_ideas']
    assert payload['status'] in {'ready_for_assessment', 'needs_review'}

    latest = client.get('/interpretations/latest')
    assert latest.status_code == 200
    assert latest.json()['interpretation_id'] == interpretation_id

    fetched = client.get(f'/interpretations/{interpretation_id}')
    assert fetched.status_code == 200
    assert fetched.json()['extracted_claims'][0].startswith('The paper compares')


def test_create_interpretation_uses_agent_when_enabled(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        interpretation_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': ['The paper compares a baseline on Titanic.'],
        },
    )
    assert create_intake.status_code == 201

    def fake_call_interpretation_agent(intake, settings, registry, store):
        return main_module.build_interpretation_record_from_agent_draft(
            intake,
            {
                'source_type': intake.source_type,
                'normalized_summary': 'agent-normalized summary',
                'extracted_method_summary': 'agent-produced method summary',
                'literature_state_summary': 'agent literature-state summary',
                'candidate_workflow_families': ['generic-tabular-benchmark'],
                'dataset_hints': ['titanic'],
                'evaluation_targets': ['baseline comparison'],
                'extracted_claims': ['Agent extracted claim'],
                'research_gaps': ['Agent gap'],
                'bounded_experiment_ideas': ['Agent idea'],
                'unresolved_questions': [],
            },
        )

    monkeypatch.setattr(main_module, 'call_interpretation_agent', fake_call_interpretation_agent)

    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201
    payload = create_interpretation.json()
    assert payload['normalized_summary'] == 'agent-normalized summary'
    assert payload['extracted_method_summary'] == 'agent-produced method summary'
    assert payload['literature_state_summary'] == 'agent literature-state summary'
    assert payload['candidate_workflow_families'] == ['generic-tabular-benchmark']
    assert payload['research_gaps'] == ['Agent gap']
    assert payload['bounded_experiment_ideas'] == ['Agent idea']
    assert payload['status'] == 'ready_for_assessment'


def test_create_interpretation_falls_back_when_agent_returns_none(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        interpretation_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': ['The paper compares a baseline on Titanic.'],
        },
    )
    assert create_intake.status_code == 201

    monkeypatch.setattr(main_module, 'call_interpretation_agent', lambda intake, settings, registry, store: None)

    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201
    payload = create_interpretation.json()
    assert 'generic-tabular-benchmark' in payload['candidate_workflow_families']
    assert payload['normalized_summary'].startswith('Read this paper intake')


def test_create_interpretation_uses_stored_source_document_context(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'paper-queue-docctx',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['site:arxiv.org machine learning agents benchmark Kaggle']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for measuring whether agents can do bounded ML engineering work on real tasks',
                        'first_jobs': ['adapt a reduced internal benchmark using 3-5 public competitions or equivalent tasks'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )

    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='doc-ctx-1',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/doc-ctx-1/source.html',
            content_type='text/html',
            size_bytes=128,
            sha256='def456',
            title='paper.html',
            text_excerpt='This paper evaluates research agents on machine learning engineering tasks using Kaggle-style benchmarks and reports accuracy improvements over a baseline.',
            session_id=session_id,
        ),
    )

    queue = client.post(
        '/paper-intake-queues/from-research-problem',
        json={
            'problem_statement': 'Find literature about research agents doing machine learning engineering work.',
            'max_candidate_papers': 1,
        },
    )
    assert queue.status_code == 201
    queue_id = queue.json()['queue_id']

    staged_intake = client.post(f'/paper-intake-queues/{queue_id}/stage-next-intake')
    assert staged_intake.status_code == 201

    interpretation = client.post('/interpretations/from-latest-intake')
    assert interpretation.status_code == 201
    payload = interpretation.json()
    assert 'Used stored source-document context.' in payload['extracted_method_summary']
    assert payload['literature_state_summary'].startswith('Current bounded literature view:')
    joined_claims = ' '.join(payload['extracted_claims']).lower()
    assert 'machine learning engineering' in joined_claims
    joined_gaps = ' '.join(payload['research_gaps']).lower()
    assert 'concrete dataset' in joined_gaps
    assert payload['bounded_experiment_ideas']


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
    assert payload['assessment_notes']

    latest = client.get('/replicability-assessments/latest')
    assert latest.status_code == 200
    assert latest.json()['assessment_id'] == assessment_id

    fetched = client.get(f'/replicability-assessments/{assessment_id}')
    assert fetched.status_code == 200
    assert fetched.json()['approval_tier'] == 'tier-2-approved-execution'


def test_create_replicability_assessment_uses_agent_when_enabled(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        assessment_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': ['The paper compares a baseline on Titanic.'],
        },
    )
    assert create_intake.status_code == 201
    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201

    def fake_call_assessment_agent(interpretation, settings, registry):
        return main_module.build_replicability_assessment_from_agent_draft(
            interpretation,
            {
                'status': 'ready_for_design',
                'recommendation': 'proceed',
                'recommended_workflow_id': 'generic-tabular-benchmark',
                'candidate_workflow_families': ['generic-tabular-benchmark'],
                'unresolved_fields': [],
                'blocking_reasons': [],
                'approval_tier': 'tier-2-approved-execution',
                'assessment_notes': ['Agent assessment note'],
            },
        )

    monkeypatch.setattr(main_module, 'call_assessment_agent', fake_call_assessment_agent)

    create_assessment = client.post('/replicability-assessments/from-latest-interpretation')
    assert create_assessment.status_code == 201
    payload = create_assessment.json()
    assert payload['status'] == 'ready_for_design'
    assert payload['recommendation'] == 'proceed'
    assert payload['assessment_notes'] == ['Agent assessment note']


def test_create_replicability_assessment_falls_back_when_agent_returns_none(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        assessment_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': ['The paper compares a baseline on Titanic.'],
        },
    )
    assert create_intake.status_code == 201
    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201

    monkeypatch.setattr(main_module, 'call_assessment_agent', lambda interpretation, settings, registry: None)

    create_assessment = client.post('/replicability-assessments/from-latest-interpretation')
    assert create_assessment.status_code == 201
    payload = create_assessment.json()
    assert payload['recommended_workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status'] == 'ready_for_design'
    assert payload['assessment_notes']


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
    create_interpretation = client.post('/interpretations/from-latest-intake')
    assert create_interpretation.status_code == 201
    interpretation_payload = create_interpretation.json()

    create_design = client.post('/design-drafts/from-latest-intake')
    assert create_design.status_code == 201
    payload = create_design.json()
    design_id = payload['design_id']
    assert payload['intake_id'] == intake_id
    assert payload['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['status'] == 'ready_for_run'
    assert payload['declared_inputs']['dataset_name'] == 'titanic'
    assert payload['unresolved_inputs'] == []
    joined_notes = ' '.join(payload['design_notes'])
    assert 'Literature state:' in joined_notes
    assert interpretation_payload['literature_state_summary'] in joined_notes
    assert 'Bounded experiment ideas:' in joined_notes

    latest = client.get('/design-drafts/latest')
    assert latest.status_code == 200
    assert latest.json()['design_id'] == design_id

    fetched = client.get(f'/design-drafts/{design_id}')
    assert fetched.status_code == 200
    assert fetched.json()['candidate_models'] == ['logistic_regression', 'random_forest']


def test_create_design_draft_from_latest_intake_uses_agent_when_enabled(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        design_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Benchmark the approved models on the Titanic dataset and validate the baseline results.',
            'notes': ['Use the standard Titanic train/test splits.'],
        },
    )
    assert create_intake.status_code == 201
    assert client.post('/interpretations/from-latest-intake').status_code == 201

    def fake_call_design_agent(intake, workflow, submitted_by, settings, source_assessment_id=None):
        return main_module.build_design_draft_from_agent_draft(
            intake,
            workflow,
            submitted_by=submitted_by,
            source_assessment_id=source_assessment_id,
            validated_draft={
                'workflow_id': workflow.workflow_id,
                'workflow_family': workflow.workflow_family,
                'objective': 'agent-produced design objective',
                'declared_inputs': {
                    'dataset_name': 'titanic',
                    'train_uri': 's3://datasets/titanic/train.csv',
                    'test_uri': 's3://datasets/titanic/test.csv',
                    'target_column': 'Survived',
                },
                'unresolved_inputs': [],
                'candidate_models': ['random_forest'],
                'resource_profile': workflow.resource_profile.profile_name,
                'expected_artifacts': workflow.expected_artifacts.model_dump(mode='json'),
                'approval_tier': workflow.approval_tier,
                'design_notes': ['Agent design note'],
            },
        )

    monkeypatch.setattr(main_module, 'call_design_agent', fake_call_design_agent)

    create_design = client.post('/design-drafts/from-latest-intake')
    assert create_design.status_code == 201
    payload = create_design.json()
    assert payload['objective'] == 'agent-produced design objective'
    assert payload['candidate_models'] == ['random_forest']
    assert payload['design_notes'] == ['Agent design note']


def test_create_design_draft_from_latest_intake_falls_back_when_agent_returns_none(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        design_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Benchmark the approved models on the Titanic dataset and validate the baseline results.',
            'notes': ['Use the standard Titanic train/test splits.'],
        },
    )
    assert create_intake.status_code == 201
    assert client.post('/interpretations/from-latest-intake').status_code == 201

    monkeypatch.setattr(main_module, 'call_design_agent', lambda *args, **kwargs: None)

    create_design = client.post('/design-drafts/from-latest-intake')
    assert create_design.status_code == 201
    payload = create_design.json()
    assert payload['declared_inputs']['dataset_name'] == 'titanic'
    assert payload['candidate_models'] == ['logistic_regression', 'random_forest']


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
    assert 'Literature state:' in ' '.join(payload['design_notes'])


def test_create_design_draft_from_latest_assessment_uses_agent_when_enabled(monkeypatch) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        design_agent_enabled=True,
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Read this paper intake and determine whether the approved Titanic benchmark path is a good fit.',
            'source_refs': ['https://example.org/titanic-paper'],
            'notes': ['The paper compares a baseline on Titanic.'],
        },
    )
    assert create_intake.status_code == 201
    assert client.post('/interpretations/from-latest-intake').status_code == 201
    create_assessment = client.post('/replicability-assessments/from-latest-interpretation')
    assert create_assessment.status_code == 201
    assessment_id = create_assessment.json()['assessment_id']

    def fake_call_design_agent(intake, workflow, submitted_by, settings, source_assessment_id=None):
        return main_module.build_design_draft_from_agent_draft(
            intake,
            workflow,
            submitted_by=submitted_by,
            source_assessment_id=source_assessment_id,
            validated_draft={
                'workflow_id': workflow.workflow_id,
                'workflow_family': workflow.workflow_family,
                'objective': 'agent-produced assessment design objective',
                'declared_inputs': {
                    'dataset_name': 'titanic',
                    'train_uri': 's3://datasets/titanic/train.csv',
                    'test_uri': 's3://datasets/titanic/test.csv',
                    'target_column': 'Survived',
                },
                'unresolved_inputs': [],
                'candidate_models': ['logistic_regression'],
                'resource_profile': workflow.resource_profile.profile_name,
                'expected_artifacts': workflow.expected_artifacts.model_dump(mode='json'),
                'approval_tier': workflow.approval_tier,
                'design_notes': ['Agent assessment-linked design note'],
            },
        )

    monkeypatch.setattr(main_module, 'call_design_agent', fake_call_design_agent)

    create_design = client.post('/design-drafts/from-latest-assessment')
    assert create_design.status_code == 201
    payload = create_design.json()
    assert payload['source_assessment_id'] == assessment_id
    assert payload['objective'] == 'agent-produced assessment design objective'
    assert payload['candidate_models'] == ['logistic_regression']


def test_create_design_draft_from_latest_assessment_requires_assessment() -> None:
    client = build_client()

    create_design = client.post('/design-drafts/from-latest-assessment')
    assert create_design.status_code == 404
    assert create_design.json()['detail'] == 'replicability assessment not found'


def test_review_latest_design_draft_resolves_literature_inputs() -> None:
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
    payload = design.json()
    assert payload['workflow_id'] == 'literature-to-experiment'
    assert payload['status'] == 'needs_review'
    assert payload['unresolved_inputs'] == ['dataset_uri']

    reviewed = client.post(
        '/design-drafts/latest/review',
        json={
            'resolved_inputs': {'dataset_uri': 's3://datasets/paper-derived/train.csv'},
            'review_notes': ['Dataset location was approved during backend review.'],
        },
    )
    assert reviewed.status_code == 200
    reviewed_payload = reviewed.json()
    assert reviewed_payload['status'] == 'ready_for_run'
    assert reviewed_payload['declared_inputs']['dataset_uri'] == 's3://datasets/paper-derived/train.csv'
    assert reviewed_payload['unresolved_inputs'] == []
    assert 'Dataset location was approved during backend review.' in reviewed_payload['design_notes']


def test_review_existing_replication_design_stays_blocked_by_approval_tier() -> None:
    client = build_client()

    intake = client.post(
        '/intakes',
        json={
            'raw_request': 'Replicate this published result from the linked repository and reported evaluation target.',
            'source_refs': ['https://example.org/paper', 'https://github.com/example/repo'],
            'notes': ['Re-run the published baseline exactly once with the approved environment.'],
        },
    )
    assert intake.status_code == 201

    design = client.post('/design-drafts/from-latest-intake')
    assert design.status_code == 201
    payload = design.json()
    assert payload['workflow_id'] == 'replication-lite'
    assert payload['status'] == 'needs_review'

    reviewed = client.post(
        f"/design-drafts/{payload['design_id']}/review",
        json={
            'resolved_inputs': {
                'repository_url': 'https://github.com/example/repo',
                'dataset_uri': 's3://datasets/replication-lite/input.csv',
                'evaluation_target': 'accuracy',
            },
            'review_notes': ['Resolved execution inputs, but keep approval-tier gate in place.'],
        },
    )
    assert reviewed.status_code == 200
    reviewed_payload = reviewed.json()
    assert reviewed_payload['status'] == 'needs_review'
    assert reviewed_payload['unresolved_inputs'] == []
    assert any('Approval tier tier-3-human-approval' in note for note in reviewed_payload['design_notes'])


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


def test_digest_schedule_lifecycle() -> None:
    client = build_client()

    created = client.post(
        '/digest-schedules',
        json={
            'cron_expr': '0 6 * * *',
            'digest_kind': 'daily-run-summary',
            'scope_filter': {'workflow_id': 'generic-tabular-benchmark'},
        },
    )
    assert created.status_code == 201
    payload = created.json()
    schedule_id = payload['schedule_id']
    assert payload['operation_type'] == 'digest'
    assert payload['approval_tier'] == 'tier-1-read-only'
    assert payload['status'] == 'active'

    listed = client.get('/digest-schedules')
    assert listed.status_code == 200
    assert [item['schedule_id'] for item in listed.json()] == [schedule_id]

    disabled = client.post(f'/digest-schedules/{schedule_id}/disable')
    assert disabled.status_code == 200
    assert disabled.json()['status'] == 'disabled'


def test_run_due_digest_schedules_creates_execution_record() -> None:
    client = build_client()

    create_run = client.post(
        '/runs',
        json={
            'workflow_id': 'generic-tabular-benchmark',
            'objective': 'Create a run for digest schedule execution.',
            'inputs': {
                'dataset_name': 'titanic',
                'train_uri': 's3://datasets/titanic/train.csv',
                'test_uri': 's3://datasets/titanic/test.csv',
                'target_column': 'Survived',
            },
            'models': ['logistic_regression'],
            'resource_profile': 'cpu-small',
        },
    )
    assert create_run.status_code == 201

    now = datetime.now(timezone.utc)
    cron_expr = f'{now.minute} {now.hour} {now.day} {now.month} {(now.weekday() + 1) % 7}'
    created = client.post(
        '/digest-schedules',
        json={
            'cron_expr': cron_expr,
            'digest_kind': 'daily-run-summary',
            'scope_filter': {'workflow_id': 'generic-tabular-benchmark'},
        },
    )
    assert created.status_code == 201
    schedule_id = created.json()['schedule_id']

    executed = client.post('/digest-schedules/run-due')
    assert executed.status_code == 200
    payload = executed.json()
    assert len(payload) == 1
    assert payload[0]['schedule_id'] == schedule_id
    assert payload[0]['result_status'] == 'ok'
    assert payload[0]['digest_payload']['matching_run_count'] == 1
    assert payload[0]['digest_payload']['workflow_ids'] == ['generic-tabular-benchmark']

    listed = client.get('/scheduled-executions')
    assert listed.status_code == 200
    executions = listed.json()
    assert len(executions) == 1
    assert executions[0]['schedule_id'] == schedule_id


def test_create_approved_rerun_schedule_from_latest_run() -> None:
    client = build_client()

    create_run = client.post(
        '/runs',
        json={
            'workflow_id': 'generic-tabular-benchmark',
            'objective': 'Create a reviewed benchmark run suitable for scheduled reruns.',
            'inputs': {
                'dataset_name': 'titanic',
                'train_uri': 's3://datasets/titanic/train.csv',
                'test_uri': 's3://datasets/titanic/test.csv',
                'target_column': 'Survived',
            },
            'models': ['logistic_regression', 'random_forest'],
            'resource_profile': 'cpu-small',
        },
    )
    assert create_run.status_code == 201
    run_id = create_run.json()['run_id']

    store = client.app.state.store
    record = store.get_run(run_id)
    succeeded_record = record.model_copy(update={'status': record.status.model_copy(update={'status': 'succeeded'})})
    store.save_run(succeeded_record)

    created = client.post(
        '/approved-rerun-schedules/from-latest-run',
        json={'cron_expr': '30 2 * * 1'},
    )
    assert created.status_code == 201
    payload = created.json()
    schedule_id = payload['schedule_id']
    assert payload['operation_type'] == 'approved-rerun'
    assert payload['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['source_run_id'] == run_id
    assert payload['allowed_dataset_uri'] == 's3://datasets/titanic/train.csv'
    assert payload['allowed_model_ids'] == ['logistic_regression', 'random_forest']

    listed = client.get('/approved-rerun-schedules')
    assert listed.status_code == 200
    assert [item['schedule_id'] for item in listed.json()] == [schedule_id]

    disabled = client.post(f'/approved-rerun-schedules/{schedule_id}/disable')
    assert disabled.status_code == 200
    assert disabled.json()['status'] == 'disabled'


def test_run_due_approved_rerun_schedules_creates_autonomous_run() -> None:
    client = build_client()

    create_run = client.post(
        '/runs',
        json={
            'workflow_id': 'generic-tabular-benchmark',
            'objective': 'Create a reviewed benchmark run suitable for scheduled reruns.',
            'inputs': {
                'dataset_name': 'titanic',
                'train_uri': 's3://datasets/titanic/train.csv',
                'test_uri': 's3://datasets/titanic/test.csv',
                'target_column': 'Survived',
            },
            'models': ['logistic_regression', 'random_forest'],
            'resource_profile': 'cpu-small',
        },
    )
    assert create_run.status_code == 201
    source_run_id = create_run.json()['run_id']

    store = client.app.state.store
    record = store.get_run(source_run_id)
    succeeded_record = record.model_copy(update={'status': record.status.model_copy(update={'status': 'succeeded'})})
    store.save_run(succeeded_record)

    now = datetime.now(timezone.utc)
    cron_expr = f'{now.minute} {now.hour} {now.day} {now.month} {(now.weekday() + 1) % 7}'
    created = client.post(
        '/approved-rerun-schedules/from-latest-run',
        json={'cron_expr': cron_expr},
    )
    assert created.status_code == 201
    schedule_id = created.json()['schedule_id']

    executed = client.post('/approved-rerun-schedules/run-due')
    assert executed.status_code == 200
    payload = executed.json()
    assert len(payload) == 1
    assert payload[0]['schedule_id'] == schedule_id
    assert payload[0]['result_status'] == 'ok'
    produced_run_id = payload[0]['produced_run_ids'][0]

    rerun_record = store.get_run(produced_run_id)
    assert rerun_record is not None
    assert rerun_record.run_purpose == 'approved-rerun'
    assert rerun_record.run_priority == 'autonomous'
    assert rerun_record.manifest.run_priority == 'autonomous'


def test_run_due_approved_rerun_schedules_resolves_source_status_from_disk(tmp_path) -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        artifacts_mount_path=str(tmp_path),
    )
    registry = WorkflowRegistry(settings.registry_dir)
    store = InMemoryRunStore()
    client = TestClient(create_app(settings=settings, registry=registry, store=store))

    create_run = client.post(
        '/runs',
        json={
            'workflow_id': 'generic-tabular-benchmark',
            'objective': 'Create a reviewed benchmark run suitable for scheduled reruns.',
            'inputs': {
                'dataset_name': 'titanic',
                'train_uri': 's3://datasets/titanic/train.csv',
                'test_uri': 's3://datasets/titanic/test.csv',
                'target_column': 'Survived',
            },
            'models': ['logistic_regression', 'random_forest'],
            'resource_profile': 'cpu-small',
        },
    )
    assert create_run.status_code == 201
    source_run_id = create_run.json()['run_id']

    run_dir = tmp_path / source_run_id
    run_dir.mkdir(parents=True)
    (run_dir / 'status.json').write_text(
        '{"run_id":"%s","status":"succeeded","updated_at":"2026-03-25T16:37:32Z","detail":"done"}'
        % source_run_id
    )

    now = datetime.now(timezone.utc)
    cron_expr = f'{now.minute} {now.hour} {now.day} {now.month} {(now.weekday() + 1) % 7}'
    created = client.post(
        '/approved-rerun-schedules/from-latest-run',
        json={'cron_expr': cron_expr},
    )
    assert created.status_code == 201
    schedule_id = created.json()['schedule_id']

    executed = client.post('/approved-rerun-schedules/run-due')
    assert executed.status_code == 200
    payload = executed.json()
    assert len(payload) == 1
    assert payload[0]['schedule_id'] == schedule_id
    assert payload[0]['result_status'] == 'ok'
    produced_run_id = payload[0]['produced_run_ids'][0]

    rerun_record = store.get_run(produced_run_id)
    assert rerun_record is not None
    assert rerun_record.run_purpose == 'approved-rerun'
    assert rerun_record.run_priority == 'autonomous'


def test_approved_rerun_schedule_requires_succeeded_tier_two_run() -> None:
    client = build_client()

    created = client.post(
        '/runs',
        json={
            'workflow_id': 'literature-to-experiment',
            'objective': 'Create a run and then force it into a failed state for schedule rejection testing.',
            'inputs': {
                'paper_id': 'https://example.org/paper-notes',
                'source_notes': 'Focus on the reviewed method and evaluation section.',
                'dataset_uri': 's3://datasets/paper-derived/train.csv',
            },
            'models': ['deterministic-template'],
            'resource_profile': 'cpu-medium',
        },
    )
    assert created.status_code == 201
    run_id = created.json()['run_id']

    store = client.app.state.store
    record = store.get_run(run_id)
    failed_record = record.model_copy(update={'status': record.status.model_copy(update={'status': 'failed'})})
    store.save_run(failed_record)

    rerun = client.post(
        '/approved-rerun-schedules/from-latest-run',
        json={'cron_expr': '15 4 * * *'},
    )
    assert rerun.status_code == 409
    assert rerun.json()['detail'] == 'latest run must be succeeded before creating an approved rerun schedule'


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


def test_create_run_from_reviewed_literature_design_draft() -> None:
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

    review = client.post(
        '/design-drafts/latest/review',
        json={
            'resolved_inputs': {'dataset_uri': 's3://datasets/paper-derived/train.csv'},
            'review_notes': ['Dataset location was approved during backend review.'],
        },
    )
    assert review.status_code == 200
    assert review.json()['status'] == 'ready_for_run'
    assert review.json()['workflow_id'] == 'literature-to-experiment'

    run = client.post('/runs/from-latest-design-draft')
    assert run.status_code == 201
    payload = run.json()
    assert payload['workflow_id'] == 'literature-to-experiment'
    assert payload['source_design_id'] == review.json()['design_id']
    assert payload['manifest']['inputs']['dataset_uri'] == 's3://datasets/paper-derived/train.csv'


def test_create_fresh_paper_pipeline_creates_literature_run_without_manual_review() -> None:
    client = build_client()

    response = client.post(
        '/paper-pipelines/fresh-paper',
        json={
            'paper_ref': 'https://example.org/papers/bounded-method.pdf',
            'raw_request': 'Ingest this paper and derive a bounded literature experiment from the linked method notes.',
            'notes': ['The paper discusses a bounded validation path for a literature-derived experiment.'],
            'dataset_uri': 's3://datasets/paper-derived/train.csv',
            'wait_for_terminal_state': False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload['assessment']['recommended_workflow_id'] == 'literature-to-experiment'
    assert payload['design']['status'] == 'ready_for_run'
    assert payload['design']['declared_inputs']['dataset_uri'] == 's3://datasets/paper-derived/train.csv'
    assert payload['run']['workflow_id'] == 'literature-to-experiment'
    assert payload['run']['run_purpose'] == 'paper-pipeline'
    assert payload['report_state']['run_status'] == 'accepted'
    assert payload['report_state']['report_available'] is True
    assert 'report.md' in payload['report_state']['artifact_names']
    assert payload['next_action'] == 'await-run-completion'


def test_create_fresh_paper_pipeline_stops_for_replication_review_boundary() -> None:
    client = build_client()

    response = client.post(
        '/paper-pipelines/fresh-paper',
        json={
            'paper_ref': 'https://github.com/example/project-paper',
            'raw_request': 'Replicate this paper from the linked repository and compare against the reported baseline.',
            'notes': ['Focus on the replication path and reported evaluation target.'],
            'wait_for_terminal_state': False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload['assessment']['recommended_workflow_id'] == 'replication-lite'
    assert payload['design']['workflow_id'] == 'replication-lite'
    assert payload['design']['status'] == 'needs_review'
    assert payload['run'] is None
    assert payload['next_action'] == 'review-required'
    assert payload['report_state']['run_status'] == 'not-submitted'


def test_create_pipeline_from_research_problem_runs_top_candidate(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    def fake_urlopen(request_obj, timeout):
        import json
        body = json.loads(request_obj.data.decode('utf-8'))
        assert body['problem_statement'].startswith('Find a bounded benchmark')
        return FakeResponse(
            {
                'request_id': 'problem-plan-1',
                'selected_tracks': [
                    {
                        'track_id': 'agent_evaluation',
                        'description': 'benchmarks for measuring ML or research-agent capability rather than just model quality',
                        'default_priority': 'P1',
                        'queries': ['site:arxiv.org machine learning agents benchmark Kaggle'],
                    }
                ],
                'selected_queries': [
                    {
                        'track': 'agent_evaluation',
                        'queries': ['site:arxiv.org machine learning agents benchmark Kaggle'],
                    }
                ],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for measuring whether agents can do bounded ML engineering work on real tasks',
                        'first_jobs': ['adapt a reduced internal benchmark using 3-5 public competitions or equivalent tasks'],
                        'tags': ['agents', 'kaggle', 'evaluation', 'ml_engineering'],
                    }
                ],
                'approved_sources': {
                    'manifest_name': 'glasslab_paper_harvester_seed_manifest',
                    'manifest_version': 1,
                    'venue_count': 9,
                    'paper_count': 12,
                    'track_query_count': 6,
                    'approved_hosts': ['arxiv.org'],
                },
                'warnings': [],
            }
        )

    monkeypatch.setattr(main_module.urllib_request, 'urlopen', fake_urlopen)

    response = client.post(
        '/paper-pipelines/from-research-problem',
        json={
            'problem_statement': 'Find a bounded benchmark for research agents doing machine learning engineering work.',
            'max_candidate_papers': 1,
            'wait_for_terminal_state': False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload['chosen_paper_id'] == 'mle_bench_arxiv_2024'
    assert payload['selected_tracks'] == ['agent_evaluation']
    assert payload['pipeline']['run']['run_purpose'] == 'paper-pipeline'
    assert payload['pipeline']['intake']['source_refs'][0] == 'https://arxiv.org/abs/2410.07095'


def test_create_pipeline_from_research_problem_returns_no_candidates(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'problem-plan-2',
                'selected_tracks': [],
                'selected_queries': [],
                'selected_papers': [],
                'approved_sources': {
                    'manifest_name': 'glasslab_paper_harvester_seed_manifest',
                    'manifest_version': 1,
                    'venue_count': 9,
                    'paper_count': 12,
                    'track_query_count': 6,
                    'approved_hosts': ['arxiv.org'],
                },
                'warnings': ['no approved seed papers matched the research problem strongly enough'],
            }
        ),
    )

    response = client.post(
        '/paper-pipelines/from-research-problem',
        json={'problem_statement': 'Solve some vague thing somehow.'},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload['pipeline'] is None
    assert payload['next_action'] == 'no-paper-candidates'
    assert payload['warnings'] == ['no approved seed papers matched the research problem strongly enough']


def test_stage_and_get_latest_research_problem() -> None:
    client = build_client()

    create = client.post(
        '/research-problems',
        json={
            'problem_statement': 'Find a bounded benchmark for research agents doing machine learning engineering work.',
            'max_candidate_papers': 2,
            'priorities': ['boundedness', 'artifact quality'],
            'submitted_by': 'operator',
        },
    )

    assert create.status_code == 201
    payload = create.json()
    assert payload['status'] == 'staged'
    assert payload['problem_statement'].startswith('Find a bounded benchmark')
    assert payload['priorities'] == ['boundedness', 'artifact quality']

    latest = client.get('/research-problems/latest')
    assert latest.status_code == 200
    assert latest.json()['problem_id'] == payload['problem_id']


def test_research_session_bootstrap_status_reports_missing_state_and_staged_problem() -> None:
    client = build_client()

    initial = client.get('/research-sessions/bootstrap-status')
    assert initial.status_code == 200
    assert initial.json() == {
        'active_session': None,
        'staged_research_problem': None,
        'recommended_next_action': 'create-session-manually',
        'can_create_session_from_latest_problem': False,
        'can_apply_session_skills': False,
        'detail': 'no active research session or staged research problem exists yet',
    }

    staged = client.post(
        '/research-problems',
        json={
            'problem_statement': 'Find a bounded benchmark for research agents doing machine learning engineering work.',
            'submitted_by': 'operator',
        },
    )
    assert staged.status_code == 201

    after_problem = client.get('/research-sessions/bootstrap-status')
    assert after_problem.status_code == 200
    payload = after_problem.json()
    assert payload['active_session'] is None
    assert payload['staged_research_problem']['problem_id'] == staged.json()['problem_id']
    assert payload['recommended_next_action'] == 'create-session-from-latest-problem'
    assert payload['can_create_session_from_latest_problem'] is True
    assert payload['can_apply_session_skills'] is False


def test_research_session_bootstrap_reports_manual_action_when_empty() -> None:
    client = build_client()

    response = client.post('/research-sessions/bootstrap')
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        'bootstrap_action': 'create-session-manually',
        'session': None,
        'staged_research_problem': None,
        'detail': 'no active research session or staged research problem exists yet',
    }


def test_research_session_bootstrap_creates_session_from_latest_problem() -> None:
    client = build_client()

    staged = client.post(
        '/research-problems',
        json={
            'problem_statement': 'Find a bounded benchmark for research agents doing machine learning engineering work.',
            'submitted_by': 'operator',
        },
    )
    assert staged.status_code == 201

    response = client.post('/research-sessions/bootstrap')
    assert response.status_code == 200
    payload = response.json()
    assert payload['bootstrap_action'] == 'created-session-from-latest-problem'
    assert payload['session']['goal_statement'].startswith('Find a bounded benchmark')
    assert payload['staged_research_problem']['problem_id'] == staged.json()['problem_id']

    latest_problem = client.get('/research-problems/latest')
    assert latest_problem.status_code == 200
    assert latest_problem.json()['session_id'] == payload['session']['session_id']

    reused = client.post('/research-sessions/bootstrap')
    assert reused.status_code == 200
    reused_payload = reused.json()
    assert reused_payload['bootstrap_action'] == 'reuse-active-session'
    assert reused_payload['session']['session_id'] == payload['session']['session_id']


def test_create_pipeline_from_latest_research_problem(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    def fake_urlopen(request_obj, timeout):
        return FakeResponse(
            {
                'request_id': 'problem-plan-latest',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['site:arxiv.org machine learning agents benchmark Kaggle']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for measuring whether agents can do bounded ML engineering work on real tasks',
                        'first_jobs': ['adapt a reduced internal benchmark using 3-5 public competitions or equivalent tasks'],
                        'tags': ['agents', 'kaggle', 'evaluation', 'ml_engineering'],
                    }
                ],
                'approved_sources': {
                    'manifest_name': 'glasslab_paper_harvester_seed_manifest',
                    'manifest_version': 1,
                    'venue_count': 9,
                    'paper_count': 12,
                    'track_query_count': 6,
                    'approved_hosts': ['arxiv.org'],
                },
                'warnings': [],
            }
        )

    monkeypatch.setattr(main_module.urllib_request, 'urlopen', fake_urlopen)

    staged = client.post(
        '/research-problems',
        json={
            'problem_statement': 'Find a bounded benchmark for research agents doing machine learning engineering work.',
            'max_candidate_papers': 1,
            'submitted_by': 'operator',
            'wait_for_terminal_state': False,
        },
    )
    assert staged.status_code == 201

    response = client.post('/paper-pipelines/from-latest-research-problem')
    assert response.status_code == 201
    payload = response.json()
    assert payload['problem_statement'].startswith('Find a bounded benchmark')
    assert payload['chosen_paper_id'] == 'mle_bench_arxiv_2024'
    assert payload['pipeline']['run']['run_purpose'] == 'paper-pipeline'


def test_create_and_fetch_paper_intake_queue(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'paper-queue-1',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['site:arxiv.org machine learning agents benchmark Kaggle']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for measuring whether agents can do bounded ML engineering work on real tasks',
                        'first_jobs': ['adapt a reduced internal benchmark using 3-5 public competitions or equivalent tasks'],
                        'tags': ['agents'],
                    },
                    {
                        'paper_id': 'second_paper',
                        'title': 'Another bounded paper',
                        'year': 2023,
                        'venue': 'arXiv',
                        'priority': 'P2',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 3,
                        'replication_complexity': 2,
                        'official_page': 'https://arxiv.org/abs/2301.00001',
                        'pdf_url': None,
                        'why_seed': 'secondary candidate',
                        'first_jobs': ['check reported setup'],
                        'tags': ['agents'],
                    },
                ],
                'warnings': [],
            }
        ),
    )

    create = client.post(
        '/paper-intake-queues/from-research-problem',
        json={
            'problem_statement': 'Find bounded literature we can stage into intake before doing deeper understanding.',
            'max_candidate_papers': 2,
            'submitted_by': 'operator',
        },
    )

    assert create.status_code == 201
    payload = create.json()
    assert payload['status'] == 'ready'
    assert len(payload['candidates']) == 2
    assert payload['candidates'][0]['intake_status'] == 'pending'

    latest = client.get('/paper-intake-queues/latest')
    assert latest.status_code == 200
    assert latest.json()['queue_id'] == payload['queue_id']

    listed = client.get('/paper-intake-queues')
    assert listed.status_code == 200
    assert listed.json()[0]['queue_id'] == payload['queue_id']


def test_stage_next_intake_from_paper_queue(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'paper-queue-2',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['site:arxiv.org machine learning agents benchmark Kaggle']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for measuring whether agents can do bounded ML engineering work on real tasks',
                        'first_jobs': ['adapt a reduced internal benchmark using 3-5 public competitions or equivalent tasks'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='doc-1',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/doc-1/source.html',
            content_type='text/html',
            size_bytes=42,
            sha256='abc123',
            title='source.html',
            session_id=session_id,
        ),
    )

    create = client.post(
        '/paper-intake-queues/from-research-problem',
        json={
            'problem_statement': 'Find bounded literature we can stage into intake before doing deeper understanding.',
            'max_candidate_papers': 1,
        },
    )
    assert create.status_code == 201
    queue_id = create.json()['queue_id']

    stage = client.post(f'/paper-intake-queues/{queue_id}/stage-next-intake')
    assert stage.status_code == 201
    intake = stage.json()
    assert intake['source_refs'][0] == 'https://arxiv.org/abs/2410.07095'
    assert intake['document_refs'] == ['doc-1']
    assert intake['status'] == 'ready_for_design'

    updated_queue = client.get(f'/paper-intake-queues/{queue_id}')
    assert updated_queue.status_code == 200
    queue_payload = updated_queue.json()
    assert queue_payload['status'] == 'exhausted'
    assert queue_payload['candidates'][0]['intake_status'] == 'staged'
    assert queue_payload['candidates'][0]['staged_intake_id'] == intake['intake_id']

    exhausted = client.post(f'/paper-intake-queues/{queue_id}/stage-next-intake')
    assert exhausted.status_code == 409
    assert exhausted.json()['detail'] == 'paper intake queue is exhausted'

    latest_document = client.get('/source-documents/latest')
    assert latest_document.status_code == 200
    assert latest_document.json()['document_id'] == 'doc-1'


def test_research_session_can_store_persistent_notes() -> None:
    client = build_client()

    create = client.post(
        '/research-sessions',
        json={
            'goal_statement': 'Investigate computer vision methods for bounded research-agent experiments.',
            'submitted_by': 'operator',
        },
    )
    assert create.status_code == 201
    session_id = create.json()['session_id']

    note = client.post(
        '/research-sessions/latest/memory',
        json={
            'working_note': 'Prioritize papers that compare alternative loss functions or curriculum strategies.',
            'decision': 'Focus the first sweep on computer vision workloads.',
            'experiment_idea': 'Compare a standard cross-entropy baseline to a focal-loss variant on the same bounded setup.',
        },
    )
    assert note.status_code == 200
    payload = note.json()
    assert payload['session_id'] == session_id
    assert 'computer vision workloads' in ' '.join(payload['decision_log'])
    assert any('focal-loss variant' in item for item in payload['next_experiment_ideas'])

    context = client.get('/research-sessions/latest/context')
    assert context.status_code == 200
    session_payload = context.json()['session']
    assert any('alternative loss functions' in item for item in session_payload['working_notes'])


def test_research_session_tracks_controlled_literature_state(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'session-queue-1',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['controlled corpus literature search']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for measuring whether agents can do bounded ML engineering work on real tasks',
                        'first_jobs': ['adapt a reduced internal benchmark using 3-5 public competitions or equivalent tasks'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='session-doc-1',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/session-doc-1/source.html',
            content_type='text/html',
            size_bytes=42,
            sha256='def456',
            title='source.html',
            text_excerpt='Controlled literature excerpt for session testing.',
            session_id=session_id,
        ),
    )

    session = client.post(
        '/research-sessions',
        json={
            'goal_statement': 'Work on a controlled-corpus literature search for bounded ML engineering benchmarks.',
            'priorities': ['controlled corpus', 'bounded experiments'],
        },
    )
    assert session.status_code == 201
    session_id = session.json()['session_id']

    problem = client.post(f'/research-sessions/{session_id}/research-problems/from-session-goal')
    assert problem.status_code == 201
    assert problem.json()['session_id'] == session_id

    queue = client.post(f'/research-sessions/{session_id}/paper-intake-queues/from-latest-problem')
    assert queue.status_code == 201
    assert queue.json()['session_id'] == session_id

    intake = client.post(f'/paper-intake-queues/{queue.json()["queue_id"]}/stage-next-intake')
    assert intake.status_code == 201
    assert intake.json()['session_id'] == session_id
    assert intake.json()['document_refs'] == ['session-doc-1']

    context = client.get('/research-sessions/latest/context')
    assert context.status_code == 200
    payload = context.json()
    assert payload['session']['session_id'] == session_id
    assert payload['session']['latest_problem_id'] == problem.json()['problem_id']
    assert payload['session']['latest_queue_id'] == queue.json()['queue_id']
    assert payload['session']['latest_document_id'] == 'session-doc-1'
    assert payload['session']['latest_intake_id'] == intake.json()['intake_id']
    assert payload['paper_intake_queue']['queue_id'] == queue.json()['queue_id']
    assert payload['source_document']['document_id'] == 'session-doc-1'


def test_research_session_skill_routes_drive_literature_flow(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'session-skill-queue-1',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['bounded literature harvest']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for bounded ML engineering work',
                        'first_jobs': ['reduce the benchmark into a smaller internal harness'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='session-skill-doc-1',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/session-skill-doc-1/source.html',
            content_type='text/html',
            size_bytes=42,
            sha256='ghi789',
            title='source.html',
            text_excerpt='Session skill route document excerpt.',
            session_id=session_id,
        ),
    )

    session = client.post(
        '/research-sessions',
        json={
            'goal_statement': 'Develop a bounded literature search around ML engineering benchmark papers.',
        },
    )
    assert session.status_code == 201
    session_id = session.json()['session_id']

    problem = client.post(f'/research-sessions/{session_id}/skills/research-problem')
    assert problem.status_code == 201
    assert problem.json()['session_id'] == session_id

    queue = client.post(f'/research-sessions/{session_id}/skills/literature-harvest')
    assert queue.status_code == 201
    assert queue.json()['session_id'] == session_id

    intake = client.post(f'/research-sessions/{session_id}/skills/paper-intake')
    assert intake.status_code == 201
    assert intake.json()['session_id'] == session_id
    assert intake.json()['document_refs'] == ['session-skill-doc-1']

    context = client.get(f'/research-sessions/{session_id}/context')
    assert context.status_code == 200
    payload = context.json()
    assert payload['session']['latest_problem_id'] == problem.json()['problem_id']
    assert payload['session']['latest_queue_id'] == queue.json()['queue_id']
    assert payload['session']['latest_document_id'] == 'session-skill-doc-1'
    assert payload['session']['latest_intake_id'] == intake.json()['intake_id']


def test_research_session_skill_routes_advance_interpretation_assessment_and_design(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'session-skill-queue-2',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['bounded literature harvest']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for bounded ML engineering work',
                        'first_jobs': ['reduce the benchmark into a smaller internal harness'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='session-skill-doc-2',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/session-skill-doc-2/source.html',
            content_type='text/html',
            size_bytes=42,
            sha256='jkl012',
            title='source.html',
            text_excerpt='Session skill route document excerpt.',
            session_id=session_id,
        ),
    )

    session = client.post(
        '/research-sessions',
        json={
            'goal_statement': 'Develop a bounded literature search around ML engineering benchmark papers.',
        },
    )
    assert session.status_code == 201
    session_id = session.json()['session_id']

    assert client.post(f'/research-sessions/{session_id}/skills/research-problem').status_code == 201
    assert client.post(f'/research-sessions/{session_id}/skills/literature-harvest').status_code == 201
    intake = client.post(f'/research-sessions/{session_id}/skills/paper-intake')
    assert intake.status_code == 201

    interpretation = client.post(f'/research-sessions/{session_id}/skills/interpretation')
    assert interpretation.status_code == 201
    assert interpretation.json()['session_id'] == session_id

    assessment = client.post(f'/research-sessions/{session_id}/skills/assessment')
    assert assessment.status_code == 201
    assert assessment.json()['session_id'] == session_id

    design = client.post(f'/research-sessions/{session_id}/skills/design')
    assert design.status_code == 201
    assert design.json()['session_id'] == session_id

    context = client.get(f'/research-sessions/{session_id}/context')
    assert context.status_code == 200
    payload = context.json()
    assert payload['session']['latest_interpretation_id'] == interpretation.json()['interpretation_id']
    assert payload['session']['latest_assessment_id'] == assessment.json()['assessment_id']
    assert payload['session']['latest_design_id'] == design.json()['design_id']


def test_research_session_read_routes_return_session_scoped_records(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'session-read-queue-1',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['bounded literature harvest']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for bounded ML engineering work',
                        'first_jobs': ['reduce the benchmark into a smaller internal harness'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='session-read-doc-1',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/session-read-doc-1/source.html',
            content_type='text/html',
            size_bytes=42,
            sha256='mno345',
            title='source.html',
            text_excerpt='Session read route document excerpt.',
            session_id=session_id,
        ),
    )

    session = client.post('/research-sessions', json={'goal_statement': 'Explore bounded ML engineering benchmark literature.'})
    assert session.status_code == 201
    session_id = session.json()['session_id']

    assert client.post(f'/research-sessions/{session_id}/skills/research-problem').status_code == 201
    queue = client.post(f'/research-sessions/{session_id}/skills/literature-harvest')
    intake = client.post(f'/research-sessions/{session_id}/skills/paper-intake')
    interpretation = client.post(f'/research-sessions/{session_id}/skills/interpretation')
    assessment = client.post(f'/research-sessions/{session_id}/skills/assessment')
    design = client.post(f'/research-sessions/{session_id}/skills/design')

    assert queue.status_code == 201
    assert intake.status_code == 201
    assert interpretation.status_code == 201
    assert assessment.status_code == 201
    assert design.status_code == 201

    assert client.get(f'/research-sessions/{session_id}/paper-intake-queue').json()['queue_id'] == queue.json()['queue_id']
    assert client.get(f'/research-sessions/{session_id}/source-document').json()['document_id'] == 'session-read-doc-1'
    assert client.get(f'/research-sessions/{session_id}/intake').json()['intake_id'] == intake.json()['intake_id']
    assert client.get(f'/research-sessions/{session_id}/interpretation').json()['interpretation_id'] == interpretation.json()['interpretation_id']
    assert client.get(f'/research-sessions/{session_id}/assessment').json()['assessment_id'] == assessment.json()['assessment_id']
    assert client.get(f'/research-sessions/{session_id}/design').json()['design_id'] == design.json()['design_id']


def test_operation_records_capture_literature_harvest_and_paper_intake(monkeypatch) -> None:
    client = build_client()

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            import json
            return json.dumps(self.payload).encode('utf-8')

    monkeypatch.setattr(
        main_module.urllib_request,
        'urlopen',
        lambda request_obj, timeout: FakeResponse(
            {
                'request_id': 'op-queue-1',
                'selected_tracks': [{'track_id': 'agent_evaluation', 'track': 'agent_evaluation'}],
                'selected_queries': [{'queries': ['operations-backed literature harvest']}],
                'selected_papers': [
                    {
                        'paper_id': 'mle_bench_arxiv_2024',
                        'title': 'MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering',
                        'year': 2024,
                        'venue': 'arXiv',
                        'priority': 'P1',
                        'tracks': ['agent_evaluation'],
                        'bounded_job_fit': 4,
                        'replication_complexity': 4,
                        'official_page': 'https://arxiv.org/abs/2410.07095',
                        'pdf_url': None,
                        'why_seed': 'benchmark for bounded ML engineering work',
                        'first_jobs': ['reduce the benchmark into a smaller internal harness'],
                        'tags': ['agents'],
                    }
                ],
                'warnings': [],
            }
        ),
    )
    monkeypatch.setattr(
        main_module,
        'ingest_source_document',
        lambda source_url, submitted_by, settings, store, session_id=None: main_module.SourceDocumentRecord(
            document_id='operations-doc-1',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri='file:///tmp/source-documents/operations-doc-1/source.html',
            content_type='text/html',
            size_bytes=42,
            sha256='jkl012',
            title='source.html',
            text_excerpt='Operation record test document excerpt.',
            session_id=session_id,
        ),
    )

    session = client.post(
        '/research-sessions',
        json={'goal_statement': 'Use operation records to inspect the literature path.'},
    )
    session_id = session.json()['session_id']
    client.post(f'/research-sessions/{session_id}/skills/research-problem')
    queue = client.post(f'/research-sessions/{session_id}/skills/literature-harvest')
    intake = client.post(f'/research-sessions/{session_id}/skills/paper-intake')

    assert queue.status_code == 201
    assert intake.status_code == 201

    operations = client.get('/operations')
    assert operations.status_code == 200
    payload = operations.json()
    operation_types = [item['operation_type'] for item in payload]
    assert 'literature-harvest' in operation_types
    assert 'source-document-fetch' in operation_types
    assert 'paper-intake' in operation_types

    latest = client.get('/operations/latest')
    assert latest.status_code == 200
    assert latest.json()['operation_type'] == 'paper-intake'
    assert latest.json()['intake_id'] == intake.json()['intake_id']


def test_resolve_intake_agent_base_url_handles_normalize_endpoint() -> None:
    settings = Settings(
        registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
        intake_agent_url='http://glasslab-intake-agent.glasslab-v2.svc.cluster.local:8090/normalize-intake',
    )
    assert (
        main_module.resolve_intake_agent_base_url(settings)
        == 'http://glasslab-intake-agent.glasslab-v2.svc.cluster.local:8090'
    )


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
    assert payload['manifest']['resource_requests'] == {'cpu': '500m', 'memory': '1Gi'}
    assert payload['manifest']['resource_limits'] == {'cpu': '1', 'memory': '2Gi'}
    assert payload['manifest']['node_selector'] == {}

    run = client.get(f'/runs/{run_id}')
    assert run.status_code == 200

    artifacts = client.get(f'/runs/{run_id}/artifacts')
    assert artifacts.status_code == 200
    assert any(item['name'] == 'report.md' for item in artifacts.json()['artifacts']['artifacts'])

    logs = client.get(f'/runs/{run_id}/logs')
    assert logs.status_code == 200
    assert logs.json()['logs'][0]['message'] == 'run accepted'


def test_workflow_execution_preflight_reports_current_contract() -> None:
    client = build_client()

    response = client.get('/workflow-families/literature-to-experiment/execution-preflight')

    assert response.status_code == 200
    payload = response.json()
    assert payload['workflow_id'] == 'literature-to-experiment'
    assert payload['resource_profile'] == 'cpu-medium'
    assert payload['runner_image'] == 'ghcr.io/offensivegeneric/glasslab-literature-runner:0.1.2'
    assert payload['resource_requests'] == {'cpu': '1', 'memory': '2Gi'}
    assert payload['resource_limits'] == {'cpu': '2', 'memory': '4Gi'}
    assert payload['job_submission_mode'] == 'null'
    assert payload['execution_status'] == 'ready'
    assert payload['submission_backend'] == 'kubernetes'
    assert payload['ready'] is True
    assert any('preflight was skipped' in warning for warning in payload['warnings'])


def test_declared_only_workflow_reports_not_executable() -> None:
    client = build_client()

    response = client.get('/workflow-families/replication-lite/execution-preflight')

    assert response.status_code == 200
    payload = response.json()
    assert payload['workflow_id'] == 'replication-lite'
    assert payload['execution_status'] == 'declared_only'
    assert payload['submission_backend'] == 'unimplemented'
    assert payload['ready'] is False
    assert any('execution_status is declared_only' in issue for issue in payload['blocking_issues'])
    assert any('submission_backend is unimplemented' in issue for issue in payload['blocking_issues'])


def test_gpu_workflow_execution_preflight_reports_gpu_contract() -> None:
    client = build_client()

    response = client.get('/workflow-families/gpu-neural-net-experiment/execution-preflight')

    assert response.status_code == 200
    payload = response.json()
    assert payload['workflow_id'] == 'gpu-neural-net-experiment'
    assert payload['resource_profile'] == 'gpu-small'
    assert payload['runner_image'] == 'ghcr.io/offensivegeneric/glasslab-gpu-experiment-runner:0.1.1'
    assert payload['resource_requests'] == {'cpu': '2', 'memory': '4Gi', 'nvidia.com/gpu': '1'}
    assert payload['resource_limits'] == {'cpu': '4', 'memory': '8Gi', 'nvidia.com/gpu': '1'}
    assert payload['node_selector'] == {
        'glasslab.io/gpu-candidate': 'true',
        'glasslab.io/gpu-vendor': 'nvidia',
    }
    assert payload['execution_status'] == 'ready'
    assert payload['submission_backend'] == 'kubernetes'
    assert payload['runtime_requirements']['gpu'] is True
    assert 'computer_vision' in payload['runtime_requirements']['modalities']
    assert payload['ready'] is True
    assert any('preflight was skipped' in warning for warning in payload['warnings'])
    assert any('torch' in warning for warning in payload['warnings'])


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
