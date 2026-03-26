from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.job_submission import NullJobSubmitter
from app.main import create_run_record, execute_due_approved_rerun_schedules, execute_due_digest_schedules
from app.persistence import InMemoryRunStore
from app.registry import WorkflowRegistry
from app.schemas import RunCreateRequest, RunRecord, ScheduledOperationRecord

REPO_ROOT = Path(__file__).resolve().parents[3]


def build_settings() -> Settings:
    return Settings(registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'))


def build_registry() -> WorkflowRegistry:
    return WorkflowRegistry(build_settings().registry_dir)


def cron_expr_for(now: datetime) -> str:
    return f'{now.minute} {now.hour} {now.day} {now.month} {(now.weekday() + 1) % 7}'


def build_digest_schedule(schedule_id: str, now: datetime) -> ScheduledOperationRecord:
    return ScheduledOperationRecord(
        schedule_id=schedule_id,
        created_at=now,
        updated_at=now,
        status='active',
        operation_type='digest',
        approval_tier='tier-1-read-only',
        owner='glasslab-operator',
        cron_expr=cron_expr_for(now),
        scope_filter={'workflow_id': 'generic-tabular-benchmark'},
        digest_kind='daily-run-summary',
    )


def build_source_run(store: InMemoryRunStore, registry: WorkflowRegistry, settings: Settings) -> RunRecord:
    workflow = registry.get_workflow('generic-tabular-benchmark')
    assert workflow is not None

    request = RunCreateRequest(
        workflow_id='generic-tabular-benchmark',
        objective='Create a reviewed benchmark run suitable for scheduled reruns.',
        inputs={
            'dataset_name': 'titanic',
            'train_uri': 's3://datasets/titanic/train.csv',
            'test_uri': 's3://datasets/titanic/test.csv',
            'target_column': 'Survived',
        },
        models=['logistic_regression'],
        resource_profile='cpu-small',
    )
    submitter = NullJobSubmitter(namespace=settings.runner_namespace)
    record = create_run_record(request, workflow, settings, submitter, store)
    succeeded_status = record.status.model_copy(
        update={
            'status': 'succeeded',
            'updated_at': record.status.updated_at,
            'detail': 'Run completed successfully.',
        }
    )
    store.save_run(record.model_copy(update={'status': succeeded_status}))
    return store.get_run(record.run_id) or record


def build_approved_rerun_schedule(
    schedule_id: str,
    now: datetime,
    source_run: RunRecord,
) -> ScheduledOperationRecord:
    return ScheduledOperationRecord(
        schedule_id=schedule_id,
        created_at=now,
        updated_at=now,
        status='active',
        operation_type='approved-rerun',
        approval_tier='tier-2-approved-execution',
        owner='glasslab-operator',
        cron_expr=cron_expr_for(now),
        scope_filter={'workflow_id': source_run.workflow_id, 'source_run_id': source_run.run_id},
        source_run_id=source_run.run_id,
        workflow_id=source_run.workflow_id,
        allowed_dataset_uri=source_run.manifest.inputs.get('train_uri'),
        allowed_model_ids=list(source_run.manifest.requested_models),
        allowed_runner_image=source_run.manifest.runner_image,
        resource_profile=source_run.manifest.resource_profile,
    )


def test_digest_schedule_run_due_is_idempotent_and_auditable() -> None:
    settings = build_settings()
    registry = build_registry()
    store = InMemoryRunStore()
    now = datetime(2026, 3, 26, 14, 30, tzinfo=timezone.utc)

    workflow = registry.get_workflow('generic-tabular-benchmark')
    assert workflow is not None
    run_request = RunCreateRequest(
        workflow_id='generic-tabular-benchmark',
        objective='Create a run for digest schedule audit coverage.',
        inputs={
            'dataset_name': 'titanic',
            'train_uri': 's3://datasets/titanic/train.csv',
            'test_uri': 's3://datasets/titanic/test.csv',
            'target_column': 'Survived',
        },
        models=['logistic_regression'],
        resource_profile='cpu-small',
    )
    submitter = NullJobSubmitter(namespace=settings.runner_namespace)
    create_run_record(run_request, workflow, settings, submitter, store)

    schedule = build_digest_schedule('digest-1', now)
    store.save_schedule(schedule)

    first = execute_due_digest_schedules(store, now)
    assert len(first) == 1
    assert first[0].schedule_id == 'digest-1'
    assert first[0].result_status == 'ok'
    assert first[0].digest_payload['matching_run_count'] == 1
    assert first[0].digest_payload['workflow_ids'] == ['generic-tabular-benchmark']

    stored_schedule = store.get_schedule('digest-1')
    assert stored_schedule is not None
    assert stored_schedule.last_result_status == 'ok'
    assert stored_schedule.last_execution_at == now
    assert stored_schedule.last_result_detail == first[0].result_detail

    second = execute_due_digest_schedules(store, now)
    assert second == []

    executions = store.list_executions(schedule_id='digest-1')
    assert len(executions) == 1
    assert executions[0].execution_id == first[0].execution_id
    assert executions[0].result_detail == first[0].result_detail


def test_approved_rerun_schedule_run_due_is_idempotent_and_auditable() -> None:
    settings = build_settings()
    registry = build_registry()
    store = InMemoryRunStore()
    now = datetime(2026, 3, 26, 15, 45, tzinfo=timezone.utc)

    source_run = build_source_run(store, registry, settings)
    schedule = build_approved_rerun_schedule('rerun-1', now, source_run)
    store.save_schedule(schedule)

    first = execute_due_approved_rerun_schedules(store, now, settings, registry, NullJobSubmitter(namespace=settings.runner_namespace))
    assert len(first) == 1
    assert first[0].schedule_id == 'rerun-1'
    assert first[0].result_status == 'ok'
    assert first[0].produced_run_ids

    produced_run_id = first[0].produced_run_ids[0]
    rerun_record = store.get_run(produced_run_id)
    assert rerun_record is not None
    assert rerun_record.run_purpose == 'approved-rerun'
    assert rerun_record.run_priority == 'autonomous'

    stored_schedule = store.get_schedule('rerun-1')
    assert stored_schedule is not None
    assert stored_schedule.last_result_status == 'ok'
    assert stored_schedule.last_execution_at == first[0].finished_at
    assert stored_schedule.last_result_detail == first[0].result_detail

    repeat_now = stored_schedule.last_execution_at
    assert repeat_now is not None

    second = execute_due_approved_rerun_schedules(
        store,
        repeat_now,
        settings,
        registry,
        NullJobSubmitter(namespace=settings.runner_namespace),
    )
    assert second == []

    executions = store.list_executions(schedule_id='rerun-1')
    assert len(executions) == 1
    assert executions[0].execution_id == first[0].execution_id
    assert executions[0].produced_run_ids == [produced_run_id]
