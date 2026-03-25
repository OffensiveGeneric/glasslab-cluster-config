import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SERVICE_ROOT / 'app'
PACKAGE_NAME = 'intake_agent_app'


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
build_normalized_draft = main_module.build_normalized_draft
build_approval_warnings = main_module.build_approval_warnings
NormalizeIntakeRequest = models_module.NormalizeIntakeRequest


def build_request() -> NormalizeIntakeRequest:
    return NormalizeIntakeRequest(
        request_id='intake-1',
        intake={
            'raw_request': 'Read this paper and turn it into a bounded benchmark request on the Titanic dataset.',
            'source_refs': ['https://example.org/paper'],
            'notes': ['Focus on the reported baseline and evaluation setup.'],
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
    assert payload['approved_sources']['manifest_name'] == 'glasslab_paper_harvester_seed_manifest'
    assert payload['approved_sources']['venue_count'] == 9


def test_approved_sources_endpoint() -> None:
    client = TestClient(app)
    response = client.get('/approved-sources')
    assert response.status_code == 200
    payload = response.json()
    assert payload['manifest_version'] == 1
    assert 'jmlr.org' in payload['approved_hosts']
    assert 'arxiv.org' in payload['approved_hosts']


def test_build_normalized_draft() -> None:
    draft = build_normalized_draft(build_request())
    assert draft.source_type == 'paper-link'
    assert draft.workflow_family_candidates == ['literature-to-experiment', 'generic-tabular-benchmark']
    assert draft.submitted_by == 'glasslab-operator'
    assert draft.normalized_summary.startswith('Read this paper and turn it into a bounded benchmark request')


def test_build_approval_warnings_for_unapproved_host() -> None:
    warnings = build_approval_warnings(build_request())
    assert warnings == [
        'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
        'source refs include hosts outside the current approved seed manifest: example.org',
    ]


def test_normalize_intake_endpoint() -> None:
    client = TestClient(app)
    response = client.post('/normalize-intake', json=build_request().model_dump())
    assert response.status_code == 200
    payload = response.json()
    assert payload['request_id'] == 'intake-1'
    assert payload['draft']['source_type'] == 'paper-link'
    assert payload['draft']['workflow_family_candidates'] == [
        'literature-to-experiment',
        'generic-tabular-benchmark',
    ]
    assert payload['approved_sources']['paper_count'] == 12
    assert payload['warnings'] == [
        'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
        'source refs include hosts outside the current approved seed manifest: example.org',
    ]
