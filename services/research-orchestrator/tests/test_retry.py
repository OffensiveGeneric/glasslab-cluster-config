"""Tests for terminal-checkpoint retry (issue #92).

Covers: storage lineage methods, workspace clone, engine retry_run,
discord rendering, and the HTTP endpoint surface.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.discord_adapter import DisabledDiscordAdapter
from app.engine import ResearchOrchestrator, WorkflowError
from app.schemas import (
    RunRecord,
    RunRetryRequest,
    RunState,
    utc_now,
)
from app.storage import ConcurrencyConflict, RecordNotFound, SqliteStore
from app.workspaces import WorkspaceError, WorkspaceManager

from conftest import RUNNER_IMAGE, create_test_repo


# ---------------------------------------------------------------------------
# Storage: create_retry_run and get_lineage
# ---------------------------------------------------------------------------


def _make_run(store: SqliteStore, *, state: RunState = RunState.CREATED) -> RunRecord:
    run_id = uuid4().hex
    now = utc_now()
    record = RunRecord(
        run_id=run_id,
        objective='test objective',
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace=f'/tmp/runs/{run_id}/beaker',
        honeydew_workspace=f'/tmp/runs/{run_id}/honeydew',
        shared_artifacts_path=f'/tmp/runs/{run_id}/shared',
        reports_path=f'/tmp/runs/{run_id}/reports',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    store.create_run(record, one_active_run=False)
    if state != RunState.CREATED:
        # Drive straight to the target via replace_run to avoid needing
        # validate_transition (state machine gaps in test scaffolding).
        stored = store.get_run(run_id)
        store.replace_run(
            stored.model_copy(update={'state': state}),
            expected_version=stored.version,
        )
    return store.get_run(run_id)


def test_create_retry_run_records_lineage(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=RunState.FAILED)
    child_id = uuid4().hex
    now = utc_now()
    child = RunRecord(
        run_id=child_id,
        parent_run_id=parent.run_id,
        objective=parent.objective,
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace=f'/tmp/runs/{child_id}/beaker',
        honeydew_workspace=f'/tmp/runs/{child_id}/honeydew',
        shared_artifacts_path=f'/tmp/runs/{child_id}/shared',
        reports_path=f'/tmp/runs/{child_id}/reports',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    result = store.create_retry_run(child, parent_run_id=parent.run_id)
    assert result.run_id == child_id
    assert result.parent_run_id == parent.run_id
    lineage = store.get_lineage(parent.run_id)
    assert len(lineage) == 1
    assert lineage[0].run_id == child_id


def test_create_retry_run_rejects_non_terminal_parent(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=RunState.CREATED)
    child_id = uuid4().hex
    now = utc_now()
    child = RunRecord(
        run_id=child_id,
        parent_run_id=parent.run_id,
        objective=parent.objective,
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace=f'/tmp/runs/{child_id}/beaker',
        honeydew_workspace=f'/tmp/runs/{child_id}/honeydew',
        shared_artifacts_path=f'/tmp/runs/{child_id}/shared',
        reports_path=f'/tmp/runs/{child_id}/reports',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ConcurrencyConflict, match='retryable terminal state'):
        store.create_retry_run(child, parent_run_id=parent.run_id)


def test_create_retry_run_rejects_complete_parent(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=RunState.COMPLETE)
    child_id = uuid4().hex
    now = utc_now()
    child = RunRecord(
        run_id=child_id,
        objective='x',
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=1,
        maximum_runtime_seconds=60,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ConcurrencyConflict, match='retryable terminal state'):
        store.create_retry_run(child, parent_run_id=parent.run_id)


def test_create_retry_run_missing_parent_raises(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    now = utc_now()
    child_id = uuid4().hex
    child = RunRecord(
        run_id=child_id,
        objective='x',
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=1,
        maximum_runtime_seconds=60,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(RecordNotFound):
        store.create_retry_run(child, parent_run_id='doesnotexist')


def test_get_lineage_returns_empty_for_no_children(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=RunState.FAILED)
    assert store.get_lineage(parent.run_id) == []


# ---------------------------------------------------------------------------
# Workspaces: clone_beaker_worktree
# ---------------------------------------------------------------------------


def test_clone_beaker_worktree_copies_files_with_digest_check(tmp_path) -> None:
    repo = create_test_repo(tmp_path)
    ws = WorkspaceManager(
        workspace_root=str(tmp_path / 'runs'),
        approved_repo_path=str(repo),
        approved_repo_ref='main',
    )
    parent_id = uuid4().hex
    child_id = uuid4().hex
    parent_paths = ws.prepare(parent_id)
    ws.prepare(child_id)

    (parent_paths.beaker / 'program.md').write_text('# Protocol\n')
    (parent_paths.beaker / 'data').mkdir()
    (parent_paths.beaker / 'data' / 'results.csv').write_text('a,b\n1,2\n')

    manifest = ws.clone_beaker_worktree(
        parent_run_id=parent_id, child_run_id=child_id
    )
    child_paths = ws.paths(child_id)

    assert 'program.md' in manifest
    assert 'data/results.csv' in manifest
    assert (child_paths.beaker / 'program.md').read_text() == '# Protocol\n'
    assert (child_paths.beaker / 'data' / 'results.csv').read_text() == 'a,b\n1,2\n'


def test_clone_beaker_worktree_copies_repo_baseline_files(tmp_path) -> None:
    # The worktree is seeded from the approved repo, so baseline files
    # (README.md, configs/baseline.yaml) are present and should be copied.
    repo = create_test_repo(tmp_path)
    ws = WorkspaceManager(
        workspace_root=str(tmp_path / 'runs'),
        approved_repo_path=str(repo),
        approved_repo_ref='main',
    )
    parent_id, child_id = uuid4().hex, uuid4().hex
    ws.prepare(parent_id)
    ws.prepare(child_id)
    manifest = ws.clone_beaker_worktree(parent_run_id=parent_id, child_run_id=child_id)
    assert 'README.md' in manifest
    assert 'configs/baseline.yaml' in manifest


def test_clone_beaker_worktree_rejects_symlinks(tmp_path) -> None:
    repo = create_test_repo(tmp_path)
    ws = WorkspaceManager(
        workspace_root=str(tmp_path / 'runs'),
        approved_repo_path=str(repo),
        approved_repo_ref='main',
    )
    parent_id, child_id = uuid4().hex, uuid4().hex
    parent_paths = ws.prepare(parent_id)
    ws.prepare(child_id)

    real_file = parent_paths.beaker / 'real.txt'
    real_file.write_text('hello')
    link = parent_paths.beaker / 'link.txt'
    link.symlink_to(real_file)

    with pytest.raises(WorkspaceError, match='symlink'):
        ws.clone_beaker_worktree(parent_run_id=parent_id, child_run_id=child_id)


# ---------------------------------------------------------------------------
# Engine: retry_run — error paths
# ---------------------------------------------------------------------------


def test_retry_run_rejects_active_parent(orchestrator_bundle) -> None:
    _, store, _, _, engine = orchestrator_bundle
    now = utc_now()
    run_id = uuid4().hex
    record = RunRecord(
        run_id=run_id,
        objective='Active run retry test.',
        state=RunState.PREPARING,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    store.create_run(record, one_active_run=False)
    with pytest.raises(WorkflowError, match='cannot retry run'):
        engine.retry_run(run_id, request=RunRetryRequest())


def test_retry_run_rejects_complete_parent(orchestrator_bundle) -> None:
    _, store, _, _, engine = orchestrator_bundle
    now = utc_now()
    run_id = uuid4().hex
    record = RunRecord(
        run_id=run_id,
        objective='Should be complete.',
        state=RunState.COMPLETE,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=1,
        maximum_runtime_seconds=60,
        maximum_parallel_jobs=1,
        active_since=None,
        created_at=now,
        updated_at=now,
    )
    store.create_run(record, one_active_run=False)
    with pytest.raises(WorkflowError, match='cannot retry run'):
        engine.retry_run(run_id, request=RunRetryRequest())


def test_retry_run_rejects_nonexistent_parent(orchestrator_bundle) -> None:
    _, _, _, _, engine = orchestrator_bundle
    with pytest.raises(Exception):
        engine.retry_run('doesnotexist', request=RunRetryRequest())


def test_retry_run_rejects_when_active_child_exists(
    orchestrator_bundle, monkeypatch
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    now = utc_now()

    parent_id = uuid4().hex
    parent = RunRecord(
        run_id=parent_id,
        objective='Wine clustering.',
        state=RunState.FAILED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=None,
        created_at=now,
        updated_at=now,
    )
    store.create_run(parent, one_active_run=False)

    child_id = uuid4().hex
    child = RunRecord(
        run_id=child_id,
        parent_run_id=parent_id,
        objective='Wine clustering.',
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    store.create_retry_run(child, parent_run_id=parent_id)

    with pytest.raises(WorkflowError, match='non-terminal child'):
        engine.retry_run(parent_id, request=RunRetryRequest())


def test_retry_run_rejects_when_no_pending_matrix_action(
    orchestrator_bundle,
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    now = utc_now()
    parent_id = uuid4().hex
    parent = RunRecord(
        run_id=parent_id,
        objective='Test.',
        state=RunState.TIMED_OUT,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=None,
        created_at=now,
        updated_at=now,
    )
    store.create_run(parent, one_active_run=False)
    with pytest.raises(WorkflowError, match='no pending experiment matrix'):
        engine.retry_run(parent_id, request=RunRetryRequest())


# ---------------------------------------------------------------------------
# Storage: retryable terminal states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('state', [RunState.FAILED, RunState.TIMED_OUT, RunState.CANCELLED])
def test_create_retry_run_accepts_all_retryable_states(tmp_path, state) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=state)
    child_id = uuid4().hex
    now = utc_now()
    child = RunRecord(
        run_id=child_id,
        parent_run_id=parent.run_id,
        objective=parent.objective,
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    result = store.create_retry_run(child, parent_run_id=parent.run_id)
    assert result.run_id == child_id
    assert store.get_lineage(parent.run_id)[0].run_id == child_id


# ---------------------------------------------------------------------------
# Storage: event log carries parent_run_id
# ---------------------------------------------------------------------------


def test_create_retry_run_event_contains_parent_run_id(tmp_path) -> None:
    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=RunState.FAILED)
    child_id = uuid4().hex
    now = utc_now()
    child = RunRecord(
        run_id=child_id,
        parent_run_id=parent.run_id,
        objective=parent.objective,
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    store.create_retry_run(child, parent_run_id=parent.run_id)
    events = store.list_events(child_id)
    created_events = [e for e in events if e.event_type == 'run.created']
    assert created_events
    assert created_events[0].payload.get('parent_run_id') == parent.run_id


# ---------------------------------------------------------------------------
# Discord: run.retry_created rendering
# ---------------------------------------------------------------------------


def test_discord_renders_retry_created_event(tmp_path) -> None:
    from app.discord_adapter import DiscordRenderer
    from app.schemas import EventRecord

    store = SqliteStore(str(tmp_path / 'db.sqlite'))
    parent = _make_run(store, state=RunState.FAILED)
    child_id = uuid4().hex
    now = utc_now()
    child = RunRecord(
        run_id=child_id,
        parent_run_id=parent.run_id,
        objective=parent.objective,
        state=RunState.CREATED,
        evaluation_contract_id='generic-research-v1',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=20,
        maximum_runtime_seconds=3600,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    store.create_retry_run(child, parent_run_id=parent.run_id)
    store.append_event(
        run_id=child_id,
        source='orchestrator',
        event_type='run.retry_created',
        payload={
            'parent_run_id': parent.run_id,
            'parent_state': 'FAILED',
            'contract_digest': 'abc123',
            'worktree_manifest_files': 3,
        },
    )
    events = store.list_events(child_id)
    retry_event = next(e for e in events if e.event_type == 'run.retry_created')

    renderer = DiscordRenderer()
    message = renderer.render(retry_event)
    assert message is not None
    assert 'Retry run created' in message.content
    assert parent.run_id[:16] in message.content
    assert 'FAILED' in message.content
    assert '3' in message.content


# ---------------------------------------------------------------------------
# State machine: PREPARING -> HONEYDEW_REVIEWING is legal
# ---------------------------------------------------------------------------


def test_preparing_to_honeydew_reviewing_is_a_valid_transition() -> None:
    from app.state_machine import validate_transition
    validate_transition(RunState.PREPARING, RunState.HONEYDEW_REVIEWING)


# ---------------------------------------------------------------------------
# Schema: RunRecord carries parent_run_id; RunRetryRequest validates bounds
# ---------------------------------------------------------------------------


def test_run_record_defaults_parent_run_id_to_none() -> None:
    now = utc_now()
    record = RunRecord(
        run_id='abc',
        objective='x',
        state=RunState.CREATED,
        evaluation_contract_id='c',
        evaluation_contract_version='1',
        evaluation_contract_digest='a' * 64,
        beaker_workspace='/x',
        honeydew_workspace='/x',
        shared_artifacts_path='/x',
        reports_path='/x',
        maximum_turns=1,
        maximum_runtime_seconds=60,
        maximum_parallel_jobs=1,
        active_since=now,
        created_at=now,
        updated_at=now,
    )
    assert record.parent_run_id is None


def test_run_retry_request_defaults_all_fields_to_none() -> None:
    req = RunRetryRequest()
    assert req.maximum_turns is None
    assert req.maximum_runtime_seconds is None
    assert req.maximum_parallel_jobs is None


def test_run_retry_request_rejects_invalid_bounds() -> None:
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        RunRetryRequest(maximum_turns=0)
    with pytest.raises(pydantic.ValidationError):
        RunRetryRequest(maximum_runtime_seconds=30)
