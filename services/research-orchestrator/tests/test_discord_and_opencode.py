from __future__ import annotations

import json

import httpx

from app.discord_adapter import DiscordHttpAdapter, DiscordRenderer
from app.config import Settings
from app.opencode_runtime import (
    OpenCodeProcessRuntime,
    extract_structured_output,
    normalize_opencode_event,
)
from app.schemas import AgentName, EventRecord


def test_discord_renderer_has_no_live_api_dependency() -> None:
    renderer = DiscordRenderer()
    message = renderer.render(
        EventRecord(
            sequence_number=1,
            run_id='run-1',
            source='honeydew',
            event_type='agent.turn_completed',
            payload={'summary': 'Protocol drafted.'},
        )
    )
    assert message is not None
    assert message.identity == 'Honeydew'
    assert message.content == 'Protocol drafted.'


def test_discord_renderer_includes_agent_handoff() -> None:
    message = DiscordRenderer().render(
        EventRecord(
            sequence_number=2,
            run_id='run-1',
            source='beaker',
            event_type='agent.turn_completed',
            payload={
                'summary': 'Implementation proposal is ready.',
                'message_to_other_agent': 'Review the proposed controls.',
            },
        )
    )

    assert message is not None
    assert message.identity == 'Beaker'
    assert '**To Honeydew:** Review the proposed controls.' in message.content


def test_discord_webhook_uses_agent_identity_and_thread() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'id': 'message-1'})

    adapter = DiscordHttpAdapter(
        bot_token='bot-token',
        channel_id='channel-1',
        webhook_url='https://discord.com/api/webhooks/webhook-id/token',
        transport=httpx.MockTransport(respond),
    )
    status_id = adapter.publish(
        thread_id='thread-1',
        status_message_id='status-1',
        event=EventRecord(
            sequence_number=3,
            run_id='run-1',
            source='honeydew',
            event_type='agent.turn_completed',
            payload={'summary': 'Methodology review complete.'},
        ),
    )

    assert status_id == 'status-1'
    assert len(requests) == 1
    assert requests[0].url.params['thread_id'] == 'thread-1'
    assert json.loads(requests[0].content)['username'] == 'Honeydew'


def test_discord_creates_public_run_thread() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={'id': 'thread-1'})

    adapter = DiscordHttpAdapter(
        bot_token='bot-token',
        channel_id='channel-1',
        transport=httpx.MockTransport(respond),
    )

    thread_id = adapter.create_thread(
        run_id='1234567890abcdef',
        objective='Compare two bounded methods.',
    )

    assert thread_id == 'thread-1'
    assert requests[0].url.path.endswith('/channels/channel-1/threads')
    assert json.loads(requests[0].content) == {
        'name': 'research-12345678',
        'type': 11,
        'auto_archive_duration': 1440,
    }
    assert 'X-Audit-Log-Reason' in requests[0].headers


def test_discord_status_message_id_is_reused() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'id': 'new-status'})

    adapter = DiscordHttpAdapter(
        bot_token='bot-token',
        channel_id='channel-1',
        transport=httpx.MockTransport(respond),
    )
    event = EventRecord(
        sequence_number=4,
        run_id='run-1',
        source='orchestrator',
        event_type='run.state_changed',
        payload={'from': 'CREATED', 'to': 'PREPARING'},
    )

    created = adapter.publish(
        thread_id='thread-1',
        status_message_id=None,
        event=event,
    )
    reused = adapter.publish(
        thread_id='thread-1',
        status_message_id=created,
        event=event,
    )

    assert created == 'new-status'
    assert reused == 'new-status'
    assert requests[0].method == 'POST'
    assert requests[1].method == 'PATCH'
    assert requests[1].url.path.endswith('/messages/new-status')


def test_opencode_event_normalization() -> None:
    normalized = normalize_opencode_event(
        {
            'type': 'permission.asked',
            'properties': {'permission': 'bash'},
        },
        run_id='run-1',
        agent=AgentName.BEAKER,
    )
    assert normalized is not None
    assert normalized[0] == 'agent.permission_requested'
    assert normalized[1]['runtime_event_type'] == 'permission.asked'
    assert normalize_opencode_event(
        {'type': 'unstable.internal.event', 'properties': {}},
        run_id='run-1',
        agent=AgentName.BEAKER,
    ) is None


def test_extracts_current_and_legacy_opencode_structured_output() -> None:
    current = {'info': {'structured': {'kind': 'protocol_draft'}}}
    legacy = {'info': {'structured_output': {'kind': 'protocol_draft'}}}

    assert extract_structured_output(current) == {'kind': 'protocol_draft'}
    assert extract_structured_output(legacy) == {'kind': 'protocol_draft'}
    assert extract_structured_output({'info': {}}) is None


def test_opencode_writable_runtime_directories_are_per_agent(
    tmp_path,
) -> None:
    runtime = OpenCodeProcessRuntime(Settings())
    workspace = tmp_path / 'run-1' / 'honeydew-worktree'
    workspace.mkdir(parents=True)

    roots = runtime._write_runtime_config(
        run_id='run-1',
        agent=AgentName.HONEYDEW,
        workspace=workspace,
    )

    assert all(path.is_dir() for path in roots)
    assert all(path.is_relative_to(tmp_path / 'run-1') for path in roots)
