import json
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SERVICE_ROOT / 'app'
PACKAGE_NAME = 'schedule_worker_app'


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


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get('/healthz')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert payload['worker_config']['workflow_api_url'].endswith(':8080')


def test_run_once_calls_workflow_api(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode('utf-8')

    def fake_urlopen(request_obj, timeout):
        if request_obj.full_url.endswith('/digest-schedules/run-due'):
            return FakeResponse(
                [
                    {
                        'execution_id': 'exec-1',
                        'schedule_id': 'sched-1',
                        'operation_type': 'digest',
                        'result_status': 'ok',
                        'result_detail': 'Digest daily-run-summary matched 2 runs.',
                        'digest_payload': {'matching_run_count': 2},
                    }
                ]
            )
        return FakeResponse(
            [
                {
                    'execution_id': 'exec-2',
                    'schedule_id': 'sched-2',
                    'operation_type': 'approved-rerun',
                    'result_status': 'ok',
                    'result_detail': 'Approved rerun submitted as run-2.',
                    'digest_payload': {},
                }
            ]
        )

    monkeypatch.setattr(main_module.urllib_request, 'urlopen', fake_urlopen)

    client = TestClient(app)
    response = client.post('/run-once')
    assert response.status_code == 200
    payload = response.json()
    assert payload['executed_count'] == 2
    assert payload['executions'][0]['schedule_id'] == 'sched-1'
    assert payload['executions'][1]['schedule_id'] == 'sched-2'
