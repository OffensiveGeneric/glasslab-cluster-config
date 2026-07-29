from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from app.discord_adapter import DiscordHttpAdapter, DiscordRenderer
from app.config import Settings
from app.discord_controls import (
    DiscordControlActor,
    DiscordControlGateway,
    DiscordControlPolicy,
    execute_discord_action,
)
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


def test_discord_pending_action_has_approval_controls() -> None:
    message = DiscordRenderer().render(
        EventRecord(
            sequence_number=3,
            run_id='run-1',
            source='orchestrator',
            event_type='action.proposed',
            payload={
                'action_id': 'action-1',
                'type': 'approve_protocol',
                'policy_classification': 'human_approval',
                'approval_status': 'pending',
                'human_approval_ready': True,
                'objective': 'Compare two bounded metric-learning methods.',
                'reason': 'Review the protocol before implementation.',
                'effect': (
                    'Authorize Beaker to implement; no cluster job is authorized.'
                ),
                'protocol_version': 1,
                'artifact': {
                    'uri': 'artifact://run-1/protocol/program.md',
                    'sha256': 'a' * 64,
                },
                'evaluation_contract': {
                    'contract_id': 'contract-1',
                    'version': '1.0.0',
                    'digest': 'b' * 64,
                },
            },
        )
    )

    assert message is not None
    assert '**Research objective**' in message.content
    assert 'Compare two bounded metric-learning methods.' in message.content
    assert '**Approval authorizes**' in message.content
    assert 'no cluster job is authorized' in message.content
    assert 'artifact://run-1/protocol/program.md' in message.content
    assert message.components is not None
    buttons = message.components[0]['components']
    assert buttons[0]['label'] == 'Approve protocol'
    assert [button['custom_id'] for button in buttons] == [
        'glasslab:approve:action-1',
        'glasslab:reject:action-1',
    ]


def test_discord_matrix_waits_for_honeydew_before_showing_controls() -> None:
    payload = {
        'action_id': 'matrix-1',
        'type': 'submit_experiment_matrix',
        'policy_classification': 'honeydew_and_human_approval',
        'approval_status': 'pending',
        'human_approval_ready': False,
        'objective': 'Compare naive and semi-hard triplet mining.',
        'reason': 'The matrix requires methodology and human approval.',
        'effect': 'Authorize bounded cluster submission.',
        'arguments': {
            'variants': [
                {'name': 'naive-mining', 'overrides': {}},
                {'name': 'semi-hard-mining', 'overrides': {}},
            ],
            'seeds': [17, 31, 49],
            'maximum_parallel_jobs': 2,
            'runner_image': 'example/runner@sha256:abc',
            'resources': {
                'cpu': 4,
                'memory_gib': 16,
                'gpus': 1,
                'wallclock_minutes': 60,
            },
        },
    }
    renderer = DiscordRenderer()

    proposed = renderer.render(
        EventRecord(
            sequence_number=4,
            run_id='run-1',
            source='beaker',
            event_type='action.proposed',
            payload=payload,
        )
    )
    assert proposed is not None
    assert 'under methodology review' in proposed.content
    assert proposed.components is None
    assert '6 jobs' in proposed.content
    assert '1 GPU' in proposed.content

    requested = renderer.render(
        EventRecord(
            sequence_number=5,
            run_id='run-1',
            source='orchestrator',
            event_type='action.human_approval_requested',
            payload={**payload, 'human_approval_ready': True},
        )
    )
    assert requested is not None
    assert 'Approval requested' in requested.content
    assert requested.components is not None
    assert (
        requested.components[0]['components'][0]['label']
        == 'Approve 6 jobs'
    )


def test_discord_control_policy_uses_guild_role_or_user_id() -> None:
    policy = DiscordControlPolicy(
        guild_id='guild-1',
        admin_role_id='role-1',
        admin_user_ids=['user-1'],
    )

    assert policy.is_authorized(
        DiscordControlActor(
            user_id='user-1',
            display_name='Tyler',
            guild_id='guild-1',
            role_ids=frozenset(),
        )
    )
    assert policy.is_authorized(
        DiscordControlActor(
            user_id='user-2',
            display_name='Mike',
            guild_id='guild-1',
            role_ids=frozenset({'role-1'}),
        )
    )
    assert not policy.is_authorized(
        DiscordControlActor(
            user_id='user-3',
            display_name='Unapproved',
            guild_id='guild-1',
            role_ids=frozenset(),
        )
    )
    assert not policy.is_authorized(
        DiscordControlActor(
            user_id='user-1',
            display_name='Tyler',
            guild_id='other-guild',
            role_ids=frozenset({'role-1'}),
        )
    )


def test_discord_control_dispatch_records_immutable_identity() -> None:
    engine = Mock()
    actor = DiscordControlActor(
        user_id='142100176322953216',
        display_name='Tyler',
        guild_id='guild-1',
        role_ids=frozenset(),
    )

    execute_discord_action(
        engine,
        operation='approve',
        action_id='action-1',
        actor=actor,
    )

    engine.approve_action.assert_called_once_with(
        'action-1',
        reviewer='discord:142100176322953216:Tyler',
        reason='Approved through Discord controls.',
    )
    engine.reject_action.assert_not_called()


def test_discord_gateway_registers_component_handler() -> None:
    gateway = DiscordControlGateway(
        engine=Mock(),
        bot_token='bot-token',
        guild_id='guild-1',
        admin_role_id='role-1',
        admin_user_ids=[],
    )

    assert gateway.client.on_interaction == gateway._on_interaction


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


def test_discord_action_controls_are_posted_by_bot() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'id': 'control-message'})

    adapter = DiscordHttpAdapter(
        bot_token='bot-token',
        channel_id='channel-1',
        webhook_url='https://discord.com/api/webhooks/webhook-id/token',
        transport=httpx.MockTransport(respond),
    )
    adapter.publish(
        thread_id='thread-1',
        status_message_id=None,
        event=EventRecord(
            sequence_number=4,
            run_id='run-1',
            source='orchestrator',
            event_type='action.proposed',
            payload={
                'action_id': 'action-1',
                'type': 'approve_protocol',
                'policy_classification': 'human_approval',
                'approval_status': 'pending',
            },
        ),
    )

    assert len(requests) == 1
    assert requests[0].url.path == '/api/v10/channels/thread-1/messages'
    payload = json.loads(requests[0].content)
    assert (
        payload['components'][0]['components'][0]['label']
        == 'Approve protocol'
    )


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
    config = json.loads((roots[0] / 'opencode' / 'opencode.json').read_text())
    assert config['lsp'] is False
    assert config['permission']['task'] == 'deny'
    assert config['permission']['websearch'] == 'deny'
    assert config['permission']['external_directory'] == 'deny'


def test_opencode_repairs_invalid_structured_output(
    tmp_path,
    monkeypatch,
) -> None:
    requests: list[httpx.Request] = []
    responses = [
        {
            'info': {
                'id': 'message-invalid',
                'structured': {
                    'kind': 'protocol_draft',
                    'summary': 'Malformed action.',
                    'requested_actions': [{'reason': 'Missing type.'}],
                },
            }
        },
        {
            'info': {
                'id': 'message-repaired',
                'structured': {
                    'kind': 'protocol_draft',
                    'summary': 'Corrected structured result.',
                    'requested_actions': [],
                },
            }
        },
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=responses[len(requests) - 1])

    runtime = OpenCodeProcessRuntime(
        Settings(opencode_structured_repair_attempts=1)
    )
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    handle = SimpleNamespace(
        base_url='http://opencode.test',
        password='password',
    )
    monkeypatch.setattr(runtime, '_start_process', lambda **_: handle)
    monkeypatch.setattr(
        runtime,
        '_client',
        lambda _: httpx.Client(
            base_url=handle.base_url,
            transport=httpx.MockTransport(respond),
        ),
    )

    result, message_id = runtime.run_turn(
        run_id='run-1',
        agent=AgentName.HONEYDEW,
        workspace=workspace,
        session_id='session-1',
        prompt='Draft the protocol.',
    )

    assert result.summary == 'Corrected structured result.'
    assert message_id == 'message-repaired'
    assert len(requests) == 2
    repair_payload = json.loads(requests[1].content)
    assert 'Correct only the structured result' in (
        repair_payload['parts'][0]['text']
    )
