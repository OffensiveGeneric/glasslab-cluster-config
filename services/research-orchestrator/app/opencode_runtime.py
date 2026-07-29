from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from pathlib import Path
import secrets
import subprocess
import time
from typing import Any, Iterator
from uuid import uuid4

import httpx
from pydantic import ValidationError

from .config import Settings
from .schemas import AgentName, AgentTurnResult


class OpenCodeRuntimeError(RuntimeError):
    pass


@dataclass
class RuntimeSession:
    runtime_id: str
    session_id: str


class AgentRuntime(ABC):
    @abstractmethod
    def ensure_session(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
        existing_session_id: str | None,
    ) -> RuntimeSession:
        raise NotImplementedError

    @abstractmethod
    def run_turn(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
        session_id: str,
        prompt: str,
    ) -> tuple[AgentTurnResult, str | None]:
        raise NotImplementedError

    @abstractmethod
    def abort(self, *, run_id: str, agent: AgentName, session_id: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return None


NORMALIZED_EVENT_TYPES = {
    'message.part.delta': 'agent.output_updated',
    'tool.pending': 'agent.tool_started',
    'tool.running': 'agent.tool_started',
    'tool.completed': 'agent.tool_completed',
    'tool.error': 'agent.tool_completed',
    'permission.asked': 'agent.permission_requested',
    'session.idle': 'agent.turn_completed',
    'session.error': 'agent.turn_completed',
}


def normalize_opencode_event(
    raw: dict[str, Any],
    *,
    run_id: str,
    agent: AgentName,
) -> tuple[str, dict[str, Any]] | None:
    raw_type = str(raw.get('type', ''))
    normalized = NORMALIZED_EVENT_TYPES.get(raw_type)
    if normalized is None:
        return None
    properties = raw.get('properties')
    if not isinstance(properties, dict):
        properties = {}
    return normalized, {
        'run_id': run_id,
        'agent': agent.value,
        'runtime_event_type': raw_type,
        'properties': properties,
    }


def extract_structured_output(body: dict[str, Any]) -> Any | None:
    """Accept the current OpenCode field and the older SDK spelling."""
    info = body.get('info')
    if not isinstance(info, dict):
        return None
    structured = info.get('structured')
    if structured is not None:
        return structured
    return info.get('structured_output')


@dataclass
class _ProcessHandle:
    runtime_id: str
    run_id: str
    agent: AgentName
    workspace: Path
    base_url: str
    password: str
    process: subprocess.Popen[str]
    log_handle: Any


class OpenCodeProcessRuntime(AgentRuntime):
    """One authenticated headless OpenCode process per run and agent."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._handles: dict[tuple[str, AgentName], _ProcessHandle] = {}
        prompt_root = Path(__file__).resolve().parents[1] / 'prompts'
        self._system_prompts = {
            AgentName.HONEYDEW: (prompt_root / 'honeydew.md').read_text(),
            AgentName.BEAKER: (prompt_root / 'beaker.md').read_text(),
        }

    def _runtime_port(self, agent: AgentName) -> int:
        return self.settings.opencode_start_port + (
            0 if agent == AgentName.HONEYDEW else 1
        )

    def _permissions(self, agent: AgentName) -> dict[str, Any]:
        denied_shell = {
            '*': 'allow',
            'kubectl *': 'deny',
            'ssh *': 'deny',
            'scp *': 'deny',
            'docker *': 'deny',
            'podman *': 'deny',
            'git push*': 'deny',
            'gh pr create*': 'deny',
            '*secret*': 'deny',
        }
        if agent == AgentName.HONEYDEW:
            denied_shell.update(
                {
                    'git commit*': 'deny',
                    'git checkout*': 'deny',
                    'git switch*': 'deny',
                }
            )
        return {
            '*': 'allow',
            'doom_loop': 'deny',
            'external_directory': 'deny',
            'lsp': 'deny',
            'question': 'deny',
            'skill': 'deny',
            'task': 'deny',
            'webfetch': 'deny',
            'websearch': 'deny',
            'bash': denied_shell,
        }

    def _write_runtime_config(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
    ) -> tuple[Path, Path, Path, Path, Path]:
        runtime_root = workspace.parent / 'runtime' / agent.value
        config_root = runtime_root / 'config'
        data_root = runtime_root / 'data'
        cache_root = runtime_root / 'cache'
        state_root = runtime_root / 'state'
        home_root = runtime_root / 'home'
        opencode_config_root = config_root / 'opencode'
        opencode_config_root.mkdir(parents=True, exist_ok=True)
        for path in (data_root, cache_root, state_root, home_root):
            path.mkdir(parents=True, exist_ok=True)
        config = {
            '$schema': 'https://opencode.ai/config.json',
            'model': f'exo/{self.settings.qwen_model_name}',
            'small_model': f'exo/{self.settings.qwen_model_name}',
            'default_agent': 'build',
            'share': 'disabled',
            'autoupdate': False,
            'lsp': False,
            'provider': {
                'exo': {
                    'npm': '@ai-sdk/openai-compatible',
                    'name': 'Glasslab Exo',
                    'options': {'baseURL': self.settings.qwen_base_url},
                    'models': {
                        self.settings.qwen_model_name: {
                            'name': self.settings.qwen_model_name,
                        }
                    },
                }
            },
            'permission': self._permissions(agent),
            'agent': {
                'build': {
                    'temperature': 0,
                    'permission': self._permissions(agent),
                },
                'plan': {'disable': True},
            },
        }
        (opencode_config_root / 'opencode.json').write_text(
            json.dumps(config, indent=2, sort_keys=True) + '\n'
        )
        return config_root, data_root, cache_root, state_root, home_root

    def _start_process(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
    ) -> _ProcessHandle:
        key = (run_id, agent)
        existing = self._handles.get(key)
        if existing is not None and existing.process.poll() is None:
            return existing
        port = self._runtime_port(agent)
        (
            config_root,
            data_root,
            cache_root,
            state_root,
            home_root,
        ) = self._write_runtime_config(
            run_id=run_id,
            agent=agent,
            workspace=workspace,
        )
        runtime_root = config_root.parent
        log_path = runtime_root / 'opencode.log'
        log_handle = log_path.open('a', encoding='utf-8')
        password = secrets.token_urlsafe(32)
        environment = {
            **__import__('os').environ,
            'XDG_CONFIG_HOME': str(config_root),
            'XDG_DATA_HOME': str(data_root),
            'XDG_CACHE_HOME': str(cache_root),
            'XDG_STATE_HOME': str(state_root),
            'HOME': str(home_root),
            'OPENCODE_SERVER_USERNAME': 'glasslab-orchestrator',
            'OPENCODE_SERVER_PASSWORD': password,
        }
        process = subprocess.Popen(
            [
                self.settings.opencode_executable,
                'serve',
                '--hostname',
                self.settings.opencode_server_host,
                '--port',
                str(port),
            ],
            cwd=workspace,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        handle = _ProcessHandle(
            runtime_id=f'opencode-{agent.value}-{uuid4().hex[:12]}',
            run_id=run_id,
            agent=agent,
            workspace=workspace,
            base_url=f'http://{self.settings.opencode_server_host}:{port}',
            password=password,
            process=process,
            log_handle=log_handle,
        )
        self._handles[key] = handle
        deadline = time.monotonic() + self.settings.opencode_start_timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise OpenCodeRuntimeError(
                    f'OpenCode process exited during startup; see {log_path}'
                )
            try:
                response = httpx.get(
                    f'{handle.base_url}/global/health',
                    auth=('glasslab-orchestrator', password),
                    timeout=1,
                )
                if response.status_code == 200:
                    return handle
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self._stop_handle(handle)
        raise OpenCodeRuntimeError('OpenCode server did not become healthy')

    def _client(self, handle: _ProcessHandle) -> httpx.Client:
        return httpx.Client(
            base_url=handle.base_url,
            auth=('glasslab-orchestrator', handle.password),
            timeout=self.settings.opencode_turn_timeout_seconds,
        )

    def ensure_session(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
        existing_session_id: str | None,
    ) -> RuntimeSession:
        handle = self._start_process(
            run_id=run_id,
            agent=agent,
            workspace=workspace,
        )
        params = {'directory': str(workspace)}
        with self._client(handle) as client:
            if existing_session_id:
                response = client.get(
                    f'/session/{existing_session_id}',
                    params=params,
                )
                if response.status_code == 200:
                    return RuntimeSession(handle.runtime_id, existing_session_id)
            response = client.post(
                '/session',
                params=params,
                json={'title': f'Glasslab {agent.value} {run_id}'},
            )
            response.raise_for_status()
            session_id = str(response.json()['id'])
        return RuntimeSession(handle.runtime_id, session_id)

    def run_turn(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
        session_id: str,
        prompt: str,
    ) -> tuple[AgentTurnResult, str | None]:
        handle = self._start_process(
            run_id=run_id,
            agent=agent,
            workspace=workspace,
        )
        message_id: str | None = None
        current_prompt = prompt
        with self._client(handle) as client:
            try:
                for attempt in range(
                    self.settings.opencode_structured_repair_attempts + 1
                ):
                    payload = {
                        'model': {
                            'providerID': 'exo',
                            'modelID': self.settings.qwen_model_name,
                        },
                        'agent': 'build',
                        'system': self._system_prompts[agent],
                        'parts': [{'type': 'text', 'text': current_prompt}],
                        'format': {
                            'type': 'json_schema',
                            'schema': AgentTurnResult.model_json_schema(),
                            'retryCount': 2,
                        },
                    }
                    response = client.post(
                        f'/session/{session_id}/message',
                        params={'directory': str(workspace)},
                        json=payload,
                    )
                    response.raise_for_status()
                    body = response.json()
                    info = body.get('info', {})
                    message_id = info.get('id')
                    structured = extract_structured_output(body)
                    if structured is None:
                        text_parts = [
                            str(part.get('text', ''))
                            for part in body.get('parts', [])
                            if part.get('type') == 'text'
                        ]
                        raw = ''.join(text_parts).strip()
                        try:
                            structured = json.loads(raw)
                        except json.JSONDecodeError as exc:
                            raise OpenCodeRuntimeError(
                                'OpenCode turn did not return structured output'
                            ) from exc
                    try:
                        return (
                            AgentTurnResult.model_validate(structured),
                            message_id,
                        )
                    except ValidationError as exc:
                        if (
                            attempt
                            >= self.settings.opencode_structured_repair_attempts
                        ):
                            raise
                        current_prompt = (
                            'Correct only the structured result from your '
                            'previous response. Do not run tools or edit files. '
                            'Return a complete object matching the supplied '
                            'JSON schema. Remove any requested action that is '
                            'not required for this turn. The independent '
                            f'validator reported:\n{exc}'
                        )
            except ValidationError as exc:
                raise OpenCodeRuntimeError(
                    'OpenCode structured output remained invalid after '
                    f'{self.settings.opencode_structured_repair_attempts} '
                    'repair attempt(s)'
                ) from exc
        raise OpenCodeRuntimeError('OpenCode turn ended without a result')

    def abort(self, *, run_id: str, agent: AgentName, session_id: str) -> None:
        handle = self._handles.get((run_id, agent))
        if handle is None or handle.process.poll() is not None:
            return
        with self._client(handle) as client:
            response = client.post(
                f'/session/{session_id}/abort',
                params={'directory': str(handle.workspace)},
            )
            if response.status_code not in {200, 404}:
                response.raise_for_status()

    def iter_normalized_events(
        self,
        *,
        run_id: str,
        agent: AgentName,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        handle = self._handles[(run_id, agent)]
        with self._client(handle).stream('GET', '/event') as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                raw = json.loads(line.removeprefix('data:').strip())
                normalized = normalize_opencode_event(
                    raw,
                    run_id=run_id,
                    agent=agent,
                )
                if normalized is not None:
                    yield normalized

    def _stop_handle(self, handle: _ProcessHandle) -> None:
        if handle.process.poll() is None:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                handle.process.kill()
                handle.process.wait(timeout=5)
        handle.log_handle.close()

    def close(self) -> None:
        for handle in list(self._handles.values()):
            self._stop_handle(handle)
        self._handles.clear()
