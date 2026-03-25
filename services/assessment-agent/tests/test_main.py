import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SERVICE_ROOT / 'app'
PACKAGE_NAME = 'assessment_agent_app'


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
build_assessment_draft = main_module.build_assessment_draft
AssessmentRequest = models_module.AssessmentRequest


def build_request() -> AssessmentRequest:
    return AssessmentRequest(
        request_id='assessment-1',
        interpretation={
            'interpretation_id': 'interp-1',
            'intake_id': 'intake-1',
            'source_type': 'paper-link',
            'normalized_summary': 'Paper-derived reproduction request.',
            'extracted_method_summary': 'Interpreted intake as generic-tabular-benchmark.',
            'literature_state_summary': 'Current bounded literature view: The paper compares a baseline on Titanic.',
            'candidate_workflow_families': ['generic-tabular-benchmark', 'literature-to-experiment'],
            'dataset_hints': ['titanic'],
            'evaluation_targets': ['baseline comparison'],
            'extracted_claims': ['The paper compares a baseline on Titanic.'],
            'research_gaps': [],
            'bounded_experiment_ideas': ['Run a bounded benchmark on titanic and compare baselines.'],
            'unresolved_questions': [],
            'submitted_by': 'glasslab-operator',
        },
        available_workflows=[
            {'workflow_id': 'generic-tabular-benchmark', 'approval_tier': 'tier-2-approved-execution'},
            {'workflow_id': 'literature-to-experiment', 'approval_tier': 'tier-1-review-required'},
        ],
    )


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json()['model_backend']['model'] == 'qwen3:30b'


def test_build_assessment_draft_prefers_ready_workflow() -> None:
    draft = build_assessment_draft(build_request())
    assert draft.recommendation == 'proceed'
    assert draft.recommended_workflow_id == 'generic-tabular-benchmark'
    assert draft.status == 'ready_for_design'
    assert draft.assessment_notes


def test_assess_interpretation_endpoint() -> None:
    client = TestClient(app)
    response = client.post('/assess-interpretation', json=build_request().model_dump())
    assert response.status_code == 200
    payload = response.json()
    assert payload['request_id'] == 'assessment-1'
    assert payload['draft']['recommended_workflow_id'] == 'generic-tabular-benchmark'
    assert payload['draft']['recommendation'] == 'proceed'
    assert payload['draft']['assessment_notes']
    assert payload['warnings'] == [
        'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
    ]
