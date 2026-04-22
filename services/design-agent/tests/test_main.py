import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SERVICE_ROOT / 'app'
PACKAGE_NAME = 'design_agent_app'


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

main_module = load_package_module(f'{PACKAGE_NAME}.main', APP_ROOT / 'main.py')
models_module = load_package_module(f'{PACKAGE_NAME}.models', APP_ROOT / 'models.py')

app = main_module.app
build_design_draft = main_module.build_design_draft
DesignRequest = models_module.DesignRequest


def build_request() -> DesignRequest:
    return DesignRequest(
        request_id='design-1',
        intake={
            'intake_id': 'intake-1',
            'source_type': 'paper-link',
            'source_refs': ['https://example.org/paper'],
            'document_refs': ['doc-1'],
            'raw_request': 'Read this paper and derive a bounded benchmark on the Titanic dataset.',
            'normalized_summary': 'Paper-derived benchmark request.',
            'workflow_family_candidates': ['literature-to-experiment', 'generic-tabular-benchmark'],
            'notes': [
                'The paper compares a baseline on Titanic.',
                'Literature state: Current bounded literature view: the paper compares a baseline on Titanic.',
                'Bounded experiment ideas: Run a bounded benchmark on titanic and compare baselines.',
            ],
            'submitted_by': 'glasslab-operator',
        },
        workflow={
            'workflow_id': 'generic-tabular-benchmark',
            'workflow_family': 'tabular-benchmark',
            'allowed_models': ['logistic_regression', 'random_forest', 'xgboost_optional'],
            'expected_artifacts': {
                'required': ['run_manifest.json', 'metrics.json'],
                'optional': ['analysis_notebook.ipynb'],
            },
            'resource_profile_name': 'cpu-small',
            'approval_tier': 'tier-2-approved-execution',
        },
    )


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get('/healthz')
    assert response.status_code == 200
    payload = response.json()
    assert payload['model_backend']['model'] == 'mlx-community/Qwen3-Coder-Next-4bit'
    assert payload['model_backend']['provider'] == 'openai-compatible'


def test_build_design_draft() -> None:
    draft = build_design_draft(build_request())
    assert draft.workflow_id == 'generic-tabular-benchmark'
    assert draft.declared_inputs['dataset_name'] == 'titanic'
    assert draft.unresolved_inputs == []
    assert draft.candidate_models == ['logistic_regression', 'random_forest']
    assert draft.design_notes
    assert any('Literature state:' in note for note in draft.design_notes)
    assert any('Bounded experiment ideas:' in note for note in draft.design_notes)


def test_draft_design_endpoint() -> None:
    client = TestClient(app)
    response = client.post('/draft-design', json=build_request().model_dump())
    assert response.status_code == 200
    payload = response.json()
    assert payload['request_id'] == 'design-1'
    assert payload['draft']['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['draft']['declared_inputs']['dataset_name'] == 'titanic'
    assert any('Literature state:' in note for note in payload['draft']['design_notes'])
    assert payload['warnings'] == [
        'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
    ]
