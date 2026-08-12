from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from app.config import Settings
from app.hermes_runtime import (
    HermesProcessRuntime,
    _HermesHandle,
    _decode_structured_output,
)
from app.main import build_agent_runtime
from app.opencode_runtime import OpenCodeProcessRuntime
from app.schemas import AgentName, TurnKind


class FakeProcess:
    def __init__(self) -> None:
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout=None) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


def _handle(tmp_path: Path) -> _HermesHandle:
    workspace = tmp_path / 'honeydew-worktree'
    workspace.mkdir()
    return _HermesHandle(
        runtime_id='hermes-honeydew-test',
        run_id='run-test',
        agent=AgentName.HONEYDEW,
        workspace=workspace,
        base_url='http://hermes.test',
        api_key='test-api-key',
        process=FakeProcess(),  # type: ignore[arg-type]
        log_handle=(tmp_path / 'hermes.log').open('a'),
    )


def test_runtime_backend_selection_is_explicit() -> None:
    assert isinstance(
        build_agent_runtime(Settings(agent_runtime_backend='opencode')),
        OpenCodeProcessRuntime,
    )
    assert isinstance(
        build_agent_runtime(Settings(agent_runtime_backend='hermes')),
        HermesProcessRuntime,
    )


def test_hermes_profiles_are_isolated_and_bounded(tmp_path: Path) -> None:
    settings = Settings()
    runtime = HermesProcessRuntime(settings)
    run_root = tmp_path / 'run'
    beaker = run_root / 'beaker-worktree'
    honeydew = run_root / 'honeydew-worktree'
    beaker.mkdir(parents=True)
    honeydew.mkdir()

    beaker_home = runtime._write_runtime_config(
        agent=AgentName.BEAKER,
        workspace=beaker,
        port=4310,
    )
    honeydew_home = runtime._write_runtime_config(
        agent=AgentName.HONEYDEW,
        workspace=honeydew,
        port=4311,
    )

    assert beaker_home != honeydew_home
    assert (beaker_home / '.no-bundled-skills').is_file()
    assert (honeydew_home / '.no-bundled-skills').is_file()
    beaker_config = yaml.safe_load((beaker_home / 'config.yaml').read_text())
    honeydew_config = yaml.safe_load(
        (honeydew_home / 'config.yaml').read_text()
    )
    assert beaker_config['terminal']['cwd'] == str(beaker)
    assert honeydew_config['terminal']['cwd'] == str(honeydew)
    assert beaker_config['terminal']['home_mode'] == 'profile'
    assert beaker_config['tools']['api_server']['enabled'] == [
        'file',
        'terminal',
    ]
    assert 'memory' in beaker_config['agent']['disabled_toolsets']
    assert 'web' in beaker_config['agent']['disabled_toolsets']
    assert 'key' not in beaker_config['gateway']['api_server']
    assert (beaker_home / 'SOUL.md').read_text() != (
        honeydew_home / 'SOUL.md'
    ).read_text()


def test_hermes_runs_api_turn_and_session_are_mocked(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    result = {
        'kind': 'protocol_draft',
        'summary': 'Drafted the protocol.',
        'produced_files': [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers['authorization'] == 'Bearer test-api-key'
        if request.method == 'GET' and request.url.path.startswith(
            '/api/sessions/'
        ):
            return httpx.Response(404)
        if request.method == 'POST' and request.url.path == '/api/sessions':
            return httpx.Response(200, json={'id': 'glasslab-honeydew-run-test'})
        if request.method == 'POST' and request.url.path == '/v1/runs':
            payload = json.loads(request.content)
            assert payload['provider'] == 'custom'
            assert payload['session_id'] == 'glasslab-honeydew-run-test'
            assert 'Return only one JSON object' in payload['input']
            return httpx.Response(200, json={'run_id': 'hermes-run-1'})
        if request.method == 'GET' and request.url.path == (
            '/v1/runs/hermes-run-1'
        ):
            return httpx.Response(
                200,
                json={'status': 'completed', 'output': json.dumps(result)},
            )
        raise AssertionError(f'unexpected request: {request.method} {request.url}')

    settings = Settings(
        hermes_poll_interval_seconds=0,
        hermes_structured_repair_attempts=0,
    )
    runtime = HermesProcessRuntime(
        settings,
        transport=httpx.MockTransport(handler),
    )
    handle = _handle(tmp_path)
    runtime._start_process = lambda **_kwargs: handle  # type: ignore[method-assign]

    session = runtime.ensure_session(
        run_id='run-test',
        agent=AgentName.HONEYDEW,
        workspace=handle.workspace,
        existing_session_id=None,
    )
    turn, message_id = runtime.run_turn(
        run_id='run-test',
        agent=AgentName.HONEYDEW,
        workspace=handle.workspace,
        session_id=session.session_id,
        prompt='Draft program.md.',
    )

    assert session.session_id == 'glasslab-honeydew-run-test'
    assert turn.kind == TurnKind.PROTOCOL_DRAFT
    assert message_id == 'hermes-run-1'
    assert ('POST', '/v1/runs') in calls


def test_hermes_abort_uses_supported_stop_endpoint(tmp_path: Path) -> None:
    stopped: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            stopped.append(request.url.path)
            return httpx.Response(200, json={'status': 'stopping'})
        raise AssertionError('unexpected request')

    runtime = HermesProcessRuntime(
        Settings(),
        transport=httpx.MockTransport(handler),
    )
    handle = _handle(tmp_path)
    runtime._handles[('run-test', AgentName.HONEYDEW)] = handle
    runtime._active_runs[('run-test', AgentName.HONEYDEW)] = 'hermes-run-1'

    runtime.abort(
        run_id='run-test',
        agent=AgentName.HONEYDEW,
        session_id='glasslab-honeydew-run-test',
    )

    assert stopped == ['/v1/runs/hermes-run-1/stop']


def test_hermes_structured_output_accepts_plain_or_fenced_json() -> None:
    payload = json.dumps(
        {'kind': 'verification', 'summary': 'Verified authoritative evidence.'}
    )

    assert _decode_structured_output(payload).kind == TurnKind.VERIFICATION
    assert _decode_structured_output(
        f'```json\n{payload}\n```'
    ).kind == TurnKind.VERIFICATION


def test_hermes_structured_output_failures_are_distinguishable() -> None:
    from app.hermes_runtime import HermesRuntimeError

    with pytest.raises(HermesRuntimeError) as not_text:
        _decode_structured_output(['not', 'a', 'string'])
    assert not_text.value.failure_class == 'not_text'

    with pytest.raises(HermesRuntimeError) as malformed:
        _decode_structured_output('this is not json')
    assert malformed.value.failure_class == 'malformed_json'

    with pytest.raises(HermesRuntimeError) as invalid:
        _decode_structured_output(
            json.dumps({'kind': 'protocol_draft', 'summary': ''})
        )
    assert invalid.value.failure_class == 'schema_invalid'
