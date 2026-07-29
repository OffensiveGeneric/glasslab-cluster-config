from __future__ import annotations

from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient
import pytest

from app.contracts import EvaluationContractResolver
from app.discord_adapter import DisabledDiscordAdapter
from app.engine import ResearchOrchestrator
from app.main import create_app
from app.mock_runtime import ScriptedMockRuntime
from app.policy import ActionPolicy
from app.schemas import ApprovalStatus, JobStatus, RunCreateRequest, RunState
from app.storage import SqliteStore
from app.workspaces import WorkspaceManager

from conftest import RUNNER_IMAGE


class DeniedThenValidRuntime(ScriptedMockRuntime):
    def run_turn(self, **kwargs):
        if (
            kwargs['agent'].value == 'beaker'
            and 'Implement the bounded' in kwargs['prompt']
        ):
            allowed_image = self.runner_image
            self.runner_image = 'example.invalid/untrusted:latest'
            try:
                return super().run_turn(**kwargs)
            finally:
                self.runner_image = allowed_image
        return super().run_turn(**kwargs)


class ContractOversizedThenValidRuntime(ScriptedMockRuntime):
    def __init__(self, *, runner_image: str) -> None:
        super().__init__(runner_image=runner_image)
        self._oversized_once = True

    def run_turn(self, **kwargs):
        result, message_id = super().run_turn(**kwargs)
        if (
            self._oversized_once
            and kwargs['agent'].value == 'beaker'
            and 'Implement the bounded' in kwargs['prompt']
        ):
            result.requested_actions[0].arguments['resources']['memory_gib'] = 2
            self._oversized_once = False
        return result, message_id


def _pending_action(store, run_id: str, action_type: str):
    return next(
        action
        for action in store.list_actions(run_id)
        if action.type == action_type
        and action.approval_status == ApprovalStatus.PENDING
    )


def _advance_to_jobs(engine, store):
    run = engine.create_run(
        RunCreateRequest(
            objective='Test the bounded orchestrator workflow with fake evidence.'
        )
    )
    protocol = _pending_action(store, run.run_id, 'approve_protocol')
    engine.approve_action(
        protocol.action_id,
        reviewer='test-human',
        reason='Protocol accepted.',
    )
    matrix = _pending_action(
        store,
        run.run_id,
        'submit_experiment_matrix',
    )
    assert matrix.honeydew_approved is True
    engine.approve_action(
        matrix.action_id,
        reviewer='test-human',
        reason='Fake execution accepted.',
    )
    return store.get_run(run.run_id)


def _complete_jobs(engine, store, cluster, run_id: str):
    for job in store.list_jobs(run_id):
        assert job.external_run_id
        cluster.complete(
            job.external_run_id,
            metrics={'score': 0.75},
        )
    return engine.reconcile_run(run_id)


def test_mocked_complete_workflow_and_agent_isolation(orchestrator_bundle) -> None:
    _, store, cluster, runtime, engine = orchestrator_bundle
    run = _advance_to_jobs(engine, store)
    assert run.state == RunState.JOB_RUNNING
    run = _complete_jobs(engine, store, cluster, run.run_id)
    assert run.state == RunState.AWAITING_FINAL_ACCEPTANCE
    final_action = _pending_action(store, run.run_id, 'accept_final_report')
    engine.approve_action(
        final_action.action_id,
        reviewer='test-human',
        reason='Report accepted.',
    )
    run = store.get_run(run.run_id)
    assert run.state == RunState.COMPLETE
    assert run.beaker_session_id != run.honeydew_session_id
    assert run.beaker_workspace != run.honeydew_workspace
    assert Path(run.protocol_path or '').is_file()
    assert (Path(run.reports_path) / 'report.md').is_file()
    assert {
        artifact.type for artifact in store.list_artifacts(run.run_id)
    } == {'protocol', 'metrics', 'report'}
    assert len(store.list_artifacts(run.run_id)) == 4
    turns = store.list_turns(run.run_id)
    assert len(turns) == 6
    assert all(turn.status == 'completed' for turn in turns)
    assert runtime.turn_counts


def test_idempotent_job_submission(orchestrator_bundle) -> None:
    _, store, cluster, _, engine = orchestrator_bundle
    run = _advance_to_jobs(engine, store)
    job = store.list_jobs(run.run_id)[0]
    first = cluster.submit(job.spec)
    second = cluster.submit(job.spec)
    assert first == second
    assert len(cluster.submissions) == len(store.list_jobs(run.run_id))
    stored, created = store.create_job_if_absent(job)
    assert created is False
    assert stored.job_id == job.job_id


def test_policy_denial_returns_beaker_to_revision(
    orchestrator_bundle,
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    engine.runtime = DeniedThenValidRuntime(runner_image=RUNNER_IMAGE)
    run = engine.create_run(
        RunCreateRequest(
            objective='Revise a policy-denied matrix without failing the run.'
        )
    )
    protocol = _pending_action(store, run.run_id, 'approve_protocol')
    engine.approve_action(
        protocol.action_id,
        reviewer='test-human',
        reason='Protocol accepted.',
    )
    run = store.get_run(run.run_id)
    assert run.state == RunState.AWAITING_EXECUTION_APPROVAL
    denied = [
        action
        for action in store.list_actions(run.run_id)
        if action.approval_status == ApprovalStatus.DENIED
    ]
    assert len(denied) == 1
    assert 'not permitted' in denied[0].reason
    assert any(
        event.event_type == 'run.state_changed'
        and event.payload.get('to') == RunState.BEAKER_REVISING.value
        for event in store.list_events(run.run_id)
    )


def test_contract_preflight_returns_beaker_to_revision(
    orchestrator_bundle,
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    engine.runtime = ContractOversizedThenValidRuntime(
        runner_image=RUNNER_IMAGE
    )
    run = engine.create_run(
        RunCreateRequest(
            objective='Reject a matrix that exceeds the evaluation contract.'
        )
    )
    protocol = _pending_action(store, run.run_id, 'approve_protocol')
    engine.approve_action(
        protocol.action_id,
        reviewer='test-human',
        reason='Protocol accepted.',
    )

    run = store.get_run(run.run_id)
    assert run.state == RunState.AWAITING_EXECUTION_APPROVAL
    rejected = [
        action
        for action in store.list_actions(run.run_id)
        if action.type == 'submit_experiment_matrix'
        and action.approval_status == ApprovalStatus.REJECTED
    ]
    assert len(rejected) == 1
    assert 'evaluation-contract resource constraints' in rejected[0].reason
    pending = _pending_action(
        store,
        run.run_id,
        'submit_experiment_matrix',
    )
    assert pending.honeydew_approved is True


def test_transient_approved_action_failure_is_persisted_and_pauses_run(
    orchestrator_bundle,
    monkeypatch,
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    run = engine.create_run(
        RunCreateRequest(
            objective='Pause safely when approved action execution fails.'
        )
    )
    protocol = _pending_action(store, run.run_id, 'approve_protocol')

    def fail_execution(_action):
        raise RuntimeError('temporary OpenCode outage')

    monkeypatch.setattr(engine, '_resume_approved_action', fail_execution)
    with pytest.raises(RuntimeError, match='temporary OpenCode outage'):
        engine.approve_action(
            protocol.action_id,
            reviewer='test-human',
            reason='Protocol accepted.',
        )

    assert store.get_run(run.run_id).state == RunState.PAUSED
    assert (
        store.get_action(protocol.action_id).approval_status
        == ApprovalStatus.APPROVED
    )
    failure = next(
        event
        for event in store.list_events(run.run_id)
        if event.event_type == 'action.execution_failed'
    )
    assert failure.payload['retryable'] is True
    assert failure.payload['jobs_created'] == 0
    assert failure.payload['resulting_state'] == RunState.PAUSED.value


def test_deterministic_matrix_execution_failure_requests_revision(
    orchestrator_bundle,
    monkeypatch,
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    run = engine.create_run(
        RunCreateRequest(
            objective='Revise after deterministic matrix execution failure.'
        )
    )
    protocol = _pending_action(store, run.run_id, 'approve_protocol')
    engine.approve_action(
        protocol.action_id,
        reviewer='test-human',
        reason='Protocol accepted.',
    )
    matrix = _pending_action(
        store,
        run.run_id,
        'submit_experiment_matrix',
    )

    def fail_submission(_action):
        raise ValueError('contract changed before submission')

    monkeypatch.setattr(engine, '_submit_matrix', fail_submission)
    with pytest.raises(ValueError, match='contract changed'):
        engine.approve_action(
            matrix.action_id,
            reviewer='test-human',
            reason='Matrix accepted.',
        )

    assert (
        store.get_action(matrix.action_id).approval_status
        == ApprovalStatus.EXECUTION_FAILED
    )
    assert store.get_run(run.run_id).state == RunState.AWAITING_EXECUTION_APPROVAL
    replacement = _pending_action(
        store,
        run.run_id,
        'submit_experiment_matrix',
    )
    assert replacement.action_id != matrix.action_id
    failure = next(
        event
        for event in store.list_events(run.run_id)
        if event.event_type == 'action.execution_failed'
    )
    assert failure.payload['retryable'] is False
    assert failure.payload['jobs_created'] == 0
    assert failure.payload['resulting_state'] == RunState.BEAKER_REVISING.value


def test_restart_recovery_from_job_running(orchestrator_bundle) -> None:
    settings, store, cluster, _, engine = orchestrator_bundle
    run = _advance_to_jobs(engine, store)
    for job in store.list_jobs(run.run_id):
        assert job.external_run_id
        cluster.complete(job.external_run_id, metrics={'score': 0.9})

    restarted_store = SqliteStore(settings.database_path)
    restarted = ResearchOrchestrator(
        settings=settings,
        store=restarted_store,
        runtime=ScriptedMockRuntime(runner_image=RUNNER_IMAGE),
        workspaces=WorkspaceManager(
            workspace_root=settings.workspace_root,
            approved_repo_path=settings.approved_repo_path,
            approved_repo_ref=settings.approved_repo_ref,
        ),
        contracts=EvaluationContractResolver(
            settings.evaluation_contract_root
        ),
        policy=ActionPolicy(
            permitted_images=settings.permitted_job_images,
            maximum_cpu=settings.maximum_cpu,
            maximum_memory_gib=settings.maximum_memory_gib,
            maximum_gpus=settings.maximum_gpus,
            maximum_parallel_jobs=settings.maximum_parallel_jobs,
        ),
        cluster=cluster,
        discord=DisabledDiscordAdapter(),
    )
    assert restarted.recover() == [run.run_id]
    recovered = restarted_store.get_run(run.run_id)
    assert recovered.state == RunState.AWAITING_FINAL_ACCEPTANCE
    assert len(restarted_store.list_artifacts(run.run_id)) == 4


def test_recovery_backfills_protocol_artifact_from_event(
    orchestrator_bundle,
) -> None:
    _, store, _, _, engine = orchestrator_bundle
    run = engine.create_run(
        RunCreateRequest(
            objective='Backfill a protocol artifact from its durable event.'
        )
    )
    protocol = store.list_artifacts(run.run_id)[0]
    with store._connect() as connection:
        connection.execute(
            'DELETE FROM artifacts WHERE artifact_id = ?',
            (protocol.artifact_id,),
        )

    assert store.list_artifacts(run.run_id) == []
    engine.recover()

    restored = store.list_artifacts(run.run_id)
    assert len(restored) == 1
    assert restored[0].type == 'protocol'
    assert restored[0].sha256 == protocol.sha256


def test_restart_recovers_submission_without_external_id(
    orchestrator_bundle,
) -> None:
    _, store, cluster, _, engine = orchestrator_bundle
    run = _advance_to_jobs(engine, store)
    job = store.list_jobs(run.run_id)[0]
    store.update_job(
        job.model_copy(
            update={
                'status': JobStatus.SUBMITTING,
                'external_run_id': None,
                'job_name': None,
                'kubernetes_uid': None,
            }
        )
    )
    engine.recover()
    recovered = store.get_job(job.job_id)
    assert recovered.status == JobStatus.RUNNING
    assert recovered.external_run_id is not None


def test_transient_inspection_error_does_not_finish_run(
    orchestrator_bundle,
) -> None:
    _, store, cluster, _, engine = orchestrator_bundle
    run = _advance_to_jobs(engine, store)
    job = store.list_jobs(run.run_id)[0]
    snapshot = cluster.snapshots.pop(job.external_run_id)
    engine.reconcile_run(run.run_id)
    assert store.get_run(run.run_id).state == RunState.JOB_RUNNING
    assert store.get_job(job.job_id).status == JobStatus.UNKNOWN
    cluster.snapshots[job.external_run_id] = snapshot
    engine.reconcile_run(run.run_id)
    assert store.get_job(job.job_id).status == JobStatus.RUNNING


def test_cancellation_aborts_sessions_and_jobs(orchestrator_bundle) -> None:
    _, store, cluster, runtime, engine = orchestrator_bundle
    run = _advance_to_jobs(engine, store)
    cancelled = engine.cancel_run(run.run_id)
    assert cancelled.state == RunState.CANCELLED
    assert len(runtime.aborted) == 2
    assert all(
        job.status.value == 'cancelled'
        for job in store.list_jobs(run.run_id)
    )
    assert all(
        cluster.inspect(job.external_run_id).status.value == 'cancelled'
        for job in store.list_jobs(run.run_id)
        if job.external_run_id
    )


def test_event_sequence_is_append_only_and_ordered(orchestrator_bundle) -> None:
    _, store, _, _, engine = orchestrator_bundle
    run = engine.create_run(
        RunCreateRequest(
            objective='Verify append-only event sequence ordering for a run.'
        )
    )
    events = store.list_events(run.run_id)
    assert [event.sequence_number for event in events] == list(
        range(1, len(events) + 1)
    )
    assert events[0].event_type == 'run.created'
    assert any(event.event_type == 'action.proposed' for event in events)


def test_http_api_with_mock_runtime(orchestrator_bundle) -> None:
    settings, store, _, _, engine = orchestrator_bundle
    app = create_app(settings, engine=engine, start_watcher=False)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/ready').status_code == 200
        response = client.post(
            '/runs',
            json={
                'objective': (
                    'Create an API-driven protocol with a mocked OpenCode turn.'
                )
            },
        )
        assert response.status_code == 201
        run_id = response.json()['run_id']
        assert response.json()['state'] == 'AWAITING_PROTOCOL_APPROVAL'
        assert client.get(f'/runs/{run_id}').status_code == 200
        events = client.get(f'/runs/{run_id}/events').json()['events']
        assert events
        action = _pending_action(store, run_id, 'approve_protocol')
        approval = client.post(
            f'/actions/{action.action_id}/approve',
            json={'reviewer': 'api-human', 'reason': 'Approved by API test.'},
        )
        assert approval.status_code == 200
        assert client.get(f'/actions/{action.action_id}').status_code == 200


def test_http_startup_does_not_wait_for_recovery(
    orchestrator_bundle,
    monkeypatch,
) -> None:
    settings, _, _, _, engine = orchestrator_bundle
    recovery_started = Event()
    release_recovery = Event()

    def blocking_recovery() -> list[str]:
        recovery_started.set()
        release_recovery.wait(timeout=5)
        return []

    monkeypatch.setattr(engine, 'recover', blocking_recovery)
    app = create_app(settings, engine=engine, start_watcher=False)
    with TestClient(app) as client:
        assert recovery_started.wait(timeout=1)
        assert client.get('/health').status_code == 200
        release_recovery.set()


def test_http_mutations_require_operator_token(orchestrator_bundle) -> None:
    settings, _, _, _, engine = orchestrator_bundle
    secured = settings.model_copy(
        update={
            'require_operator_auth': True,
            'operator_api_token': 'test-operator-token',
        }
    )
    app = create_app(secured, engine=engine, start_watcher=False)
    payload = {
        'objective': 'Create a secured API-driven research protocol.'
    }
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.post('/runs', json=payload).status_code == 401
        response = client.post(
            '/runs',
            json=payload,
            headers={
                'X-Glasslab-Operator-Token': 'test-operator-token'
            },
        )
        assert response.status_code == 201
