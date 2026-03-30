import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SERVICE_ROOT / 'app'
PACKAGE_NAME = 'interpretation_agent_app'


def load_package_module(module_name: str, path: Path):
    spec = spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(APP_ROOT)]
sys.modules[PACKAGE_NAME] = package

models_module = load_package_module(f'{PACKAGE_NAME}.models', APP_ROOT / 'models.py')
main_module = load_package_module(f'{PACKAGE_NAME}.main', APP_ROOT / 'main.py')

app = main_module.app
build_interpretation_draft = main_module.build_interpretation_draft
interpret_with_backends = main_module.interpret_with_backends
InterpretationRequest = models_module.InterpretationRequest


def build_request() -> InterpretationRequest:
    return InterpretationRequest(
        request_id='intake-1',
        intake={
            'intake_id': 'intake-1',
            'source_type': 'paper-link',
            'source_refs': ['https://example.org/paper'],
            'document_refs': ['doc-1'],
            'raw_request': 'Read this paper and propose a bounded reproduction path for the Titanic benchmark.',
            'normalized_summary': 'Paper-derived reproduction request for a bounded benchmark.',
            'workflow_family_candidates': ['literature-to-experiment', 'replication-lite', 'generic-tabular-benchmark'],
            'notes': [
                'The paper compares a baseline on Titanic.',
                'Focus on the reported metrics and evaluation method.',
            ],
            'submitted_by': 'glasslab-operator',
        },
    )


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get('/healthz')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['model_backend']['model'] == 'qwen3:30b'


def test_build_interpretation_draft_prefers_matching_candidates() -> None:
    draft = build_interpretation_draft(build_request())

    assert draft.candidate_workflow_families[0] == 'generic-tabular-benchmark'
    assert 'titanic' in draft.dataset_hints
    assert 'reported metrics' in draft.evaluation_targets
    assert draft.literature_state_summary.startswith('Current bounded literature view:')
    assert draft.extracted_claims[0].startswith('The paper compares')
    assert draft.bounded_experiment_ideas


def test_interpret_intake_endpoint_returns_bounded_draft_shape(monkeypatch) -> None:
    def fake_interpret_with_backends(request):
        return (
            build_interpretation_draft(request),
            main_module.PRIMARY_BACKEND.metadata(),
            ['stubbed interpretation backend'],
        )

    monkeypatch.setattr(main_module, 'interpret_with_backends', fake_interpret_with_backends)
    client = TestClient(app)
    response = client.post('/interpret-intake', json=build_request().model_dump())

    assert response.status_code == 200
    payload = response.json()
    assert payload['request_id'] == 'intake-1'
    assert payload['draft']['source_type'] == 'paper-link'
    assert payload['draft']['candidate_workflow_families'][0] == 'generic-tabular-benchmark'
    assert payload['draft']['literature_state_summary'].startswith('Current bounded literature view:')
    assert 'research_gaps' in payload['draft']
    assert payload['draft']['bounded_experiment_ideas']
    assert payload['model_backend']['provider'] == 'ollama'
    assert payload['warnings'] == ['stubbed interpretation backend']


def test_interpretation_agent_uses_fallback_backend(monkeypatch) -> None:
    request = build_request()
    calls: list[str] = []

    def fake_call_backend(req, backend):
        calls.append(backend.base_url)
        if backend.base_url.endswith('.23:11434'):
            raise ValueError('primary unavailable')
        draft = build_interpretation_draft(req)
        draft.extracted_method_summary = 'Fallback model interpretation.'
        return draft

    monkeypatch.setattr(main_module, 'call_backend', fake_call_backend)
    draft, backend, warnings = interpret_with_backends(request)

    assert draft.extracted_method_summary == 'Fallback model interpretation.'
    assert backend.base_url == 'http://192.168.1.12:11434'
    assert calls == ['http://192.168.1.23:11434', 'http://192.168.1.12:11434']
    assert 'used fallback interpretation backend' in warnings


def test_interpretation_agent_falls_back_to_deterministic_scaffold(monkeypatch) -> None:
    request = build_request()

    def failing_call_backend(_req, _backend):
        raise ValueError('backend failed')

    monkeypatch.setattr(main_module, 'call_backend', failing_call_backend)
    draft, backend, warnings = interpret_with_backends(request)

    assert draft.candidate_workflow_families[0] == 'generic-tabular-benchmark'
    assert backend.base_url == 'http://192.168.1.23:11434'
    assert any('all model backends failed' in warning for warning in warnings)
