from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .config import Settings
from .job_submission import JobSubmitter
from .persistence import RunStore
from .run_artifacts import resolve_run_status
from .schemas import (
    DigestScheduleCreateRequest,
    ScheduledExecutionRecord,
    ScheduledOperationRecord,
)


def build_digest_schedule(request: DigestScheduleCreateRequest, settings: Settings) -> ScheduledOperationRecord:
    now = datetime.now(timezone.utc)
    return ScheduledOperationRecord(
        schedule_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status='active',
        operation_type='digest',
        approval_tier='tier-1-read-only',
        owner=request.owner or settings.default_submitted_by,
        cron_expr=request.cron_expr.strip(),
        scope_filter=request.scope_filter,
        digest_kind=request.digest_kind.strip(),
    )


def disable_schedule(record: ScheduledOperationRecord) -> ScheduledOperationRecord:
    now = datetime.now(timezone.utc)
    return record.model_copy(
        update={
            'status': 'disabled',
            'updated_at': now,
            'last_result_status': record.last_result_status or 'disabled',
            'last_result_detail': record.last_result_detail or 'Disabled by operator action.',
        }
    )


def cron_field_matches(field: str, value: int) -> bool:
    field = field.strip()
    if field == '*':
        return True
    allowed_values: set[int] = set()
    for token in field.split(','):
        token = token.strip()
        if not token:
            continue
        if token == '*':
            return True
        if token.isdigit():
            allowed_values.add(int(token))
    return value in allowed_values


def schedule_is_due(record: ScheduledOperationRecord, now: datetime) -> bool:
    if record.status != 'active':
        return False
    fields = record.cron_expr.split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    weekday_value = (now.weekday() + 1) % 7
    return all(
        (
            cron_field_matches(minute, now.minute),
            cron_field_matches(hour, now.hour),
            cron_field_matches(day, now.day),
            cron_field_matches(month, now.month),
            cron_field_matches(weekday, weekday_value),
        )
    )


def execute_due_digest_schedules(
    store: RunStore,
    now: datetime,
) -> list[ScheduledExecutionRecord]:
    executions: list[ScheduledExecutionRecord] = []
    all_runs = store.list_runs()
    for schedule in store.list_schedules(operation_type='digest'):
        if not schedule_is_due(schedule, now):
            continue
        if schedule.last_execution_at is not None:
            last = schedule.last_execution_at.astimezone(timezone.utc)
            if last.year == now.year and last.month == now.month and last.day == now.day and last.hour == now.hour and last.minute == now.minute:
                continue

        matching_runs = all_runs
        workflow_id = schedule.scope_filter.get('workflow_id')
        run_status = schedule.scope_filter.get('run_status')
        if isinstance(workflow_id, str) and workflow_id.strip():
            matching_runs = [run for run in matching_runs if run.workflow_id == workflow_id.strip()]
        if isinstance(run_status, str) and run_status.strip():
            matching_runs = [run for run in matching_runs if run.status.status == run_status.strip()]

        payload = {
            'digest_kind': schedule.digest_kind,
            'matching_run_count': len(matching_runs),
            'workflow_ids': sorted({run.workflow_id for run in matching_runs}),
            'run_status_counts': {},
        }
        status_counts: dict[str, int] = {}
        for run in matching_runs:
            status_counts[run.status.status] = status_counts.get(run.status.status, 0) + 1
        payload['run_status_counts'] = status_counts

        started_at = now
        finished_at = now
        detail = f"Digest {schedule.digest_kind} matched {len(matching_runs)} runs."
        execution = ScheduledExecutionRecord(
            execution_id=uuid4().hex,
            schedule_id=schedule.schedule_id,
            operation_type=schedule.operation_type,
            started_at=started_at,
            finished_at=finished_at,
            result_status='ok',
            result_detail=detail,
            produced_run_ids=[],
            digest_payload=payload,
        )
        store.save_execution(execution)
        updated_schedule = schedule.model_copy(
            update={
                'updated_at': finished_at,
                'last_execution_at': finished_at,
                'last_result_status': 'ok',
                'last_result_detail': detail,
            }
        )
        store.save_schedule(updated_schedule)
        executions.append(execution)
    return executions
