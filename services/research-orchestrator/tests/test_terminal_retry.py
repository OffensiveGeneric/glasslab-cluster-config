from __future__ import annotations

from pathlib import Path

import pytest

from app.engine import WorkflowError
from app.schemas import ApprovalStatus, RunCreateRequest, RunState, TerminalRetryRequest


def _terminal_parent(engine, store):
    parent = engine.create_run(RunCreateRequest(objective='Verify terminal retry checkpoint isolation.'))
    protocol_action = next(
        action for action in store.list_actions(parent.run_id)
        if action.type == 'approve_protocol'
    )
    store.update_action(
        protocol_action.action_id,
        approval_status=ApprovalStatus.APPROVED,
        reviewer='test-reviewer',
        reason='Approved checkpoint for terminal retry test.',
    )
    store.transition_run(parent.run_id, RunState.FAILED)
    return store.get_run(parent.run_id)


def test_terminal_retry_creates_fresh_child_and_renews_protocol_approval(orchestrator_bundle):
    settings, store, _, _, engine = orchestrator_bundle
    parent = _terminal_parent(engine, store)
    before = parent.model_dump(mode='json')

    child = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())

    assert child.parent_run_id == parent.run_id
    assert child.state == RunState.AWAITING_PROTOCOL_APPROVAL
    assert child.turn_number == 0
    assert child.beaker_session_id is None and child.honeydew_session_id is None
    assert child.maximum_turns == settings.maximum_turns
    assert not store.list_jobs(child.run_id)
    actions = store.list_actions(child.run_id)
    assert [(a.type, a.approval_status) for a in actions] == [
        ('approve_protocol', ApprovalStatus.PENDING)
    ]
    assert store.get_run(parent.run_id).model_dump(mode='json') == before
    assert any(e.event_type == 'run.retry_created' for e in store.list_events(parent.run_id))
    assert any(e.event_type == 'run.retry_created' for e in store.list_events(child.run_id))


def test_terminal_retry_is_idempotent_and_recovery_is_safe(orchestrator_bundle):
    _, store, _, _, engine = orchestrator_bundle
    parent = _terminal_parent(engine, store)
    first = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
    second = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
    assert second.run_id == first.run_id
    action_count = len(store.list_actions(first.run_id))
    assert first.run_id in engine.recover()
    assert len(store.list_actions(first.run_id)) == action_count


@pytest.mark.parametrize('state', [RunState.CREATED, RunState.CANCELLED, RunState.COMPLETE])
def test_terminal_retry_rejects_ineligible_source(orchestrator_bundle, state):
    _, store, _, _, engine = orchestrator_bundle
    parent = engine.create_run(RunCreateRequest(objective='Reject nonterminal retry source state.'))
    if state == RunState.COMPLETE:
        store.replace_run(parent.model_copy(update={'state': state}), expected_version=parent.version)
    elif state != RunState.CREATED:
        store.transition_run(parent.run_id, state)
    with pytest.raises(WorkflowError):
        engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())


@pytest.mark.parametrize('tamper', ['protocol', 'manifest'])
def test_terminal_retry_fails_closed_on_tampered_checkpoint(orchestrator_bundle, tamper):
    _, store, _, _, engine = orchestrator_bundle
    parent = _terminal_parent(engine, store)
    if tamper == 'protocol':
        Path(parent.protocol_path).write_text('tampered\n', encoding='utf-8')
        with pytest.raises(WorkflowError, match='checksum'):
            engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
    else:
        child = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
        checkpoint = Path(child.beaker_workspace).parent / 'events' / 'terminal-retry-checkpoint.json'
        checkpoint.write_text('{}\n', encoding='utf-8')
        current = store.get_run(child.run_id)
        store.replace_run(current.model_copy(update={'state': RunState.PREPARING}), expected_version=current.version)
        with pytest.raises(Exception, match='checkpoint'):
            engine._resume_terminal_retry(child.run_id)


def test_terminal_retry_does_not_inherit_pending_actions_or_jobs(orchestrator_bundle):
    _, store, _, _, engine = orchestrator_bundle
    parent = _terminal_parent(engine, store)
    assert store.list_actions(parent.run_id)
    child = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
    assert {a.type for a in store.list_actions(child.run_id)} == {'approve_protocol'}
    assert store.list_jobs(child.run_id) == []


def test_terminal_retry_requires_parent_protocol_approval(orchestrator_bundle):
    _, store, _, _, engine = orchestrator_bundle
    parent = engine.create_run(RunCreateRequest(objective='Require fresh approval for retry source protocol.'))
    store.transition_run(parent.run_id, RunState.FAILED)
    with pytest.raises(WorkflowError, match='human-approved'):
        engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())


def test_discord_failure_does_not_lose_retry_state(orchestrator_bundle, monkeypatch):
    _, store, _, _, engine = orchestrator_bundle
    parent = _terminal_parent(engine, store)
    monkeypatch.setattr(engine.discord, 'publish', lambda **_: (_ for _ in ()).throw(RuntimeError('offline')))
    child = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
    assert store.get_run(child.run_id).state == RunState.AWAITING_PROTOCOL_APPROVAL
    assert any(event.event_type == 'run.retry_created' for event in store.list_events(parent.run_id))


def test_retry_recovery_does_not_duplicate_action_or_event(orchestrator_bundle, monkeypatch):
    _, store, _, _, engine = orchestrator_bundle
    parent = _terminal_parent(engine, store)
    child = engine.retry_terminal_run(parent.run_id, TerminalRetryRequest())
    current = store.get_run(child.run_id)
    store.replace_run(current.model_copy(update={'state': RunState.PREPARING}), expected_version=current.version)
    before_events = len(store.list_events(child.run_id))
    engine.recover()
    assert len(store.list_actions(child.run_id)) == 1
    assert len(store.list_events(child.run_id)) == before_events + 1  # state transition only
