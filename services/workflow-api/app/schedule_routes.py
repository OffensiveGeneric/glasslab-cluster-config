from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, HTTPException, status

from .config import Settings
from .digest_scheduling import build_digest_schedule, disable_schedule, execute_due_digest_schedules
from .job_submission import JobSubmitter
from .persistence import RunStore
from .registry import WorkflowRegistry
from .run_artifacts import resolve_run_status
from .schemas import (
    ApprovedRerunScheduleCreateRequest,
    DigestScheduleCreateRequest,
    ScheduledExecutionRecord,
    ScheduledOperationRecord,
)


def register_schedule_routes(
    app: FastAPI,
    *,
    settings: Settings,
    registry: WorkflowRegistry,
    store: RunStore,
    submitter: JobSubmitter,
    build_approved_rerun_schedule: Callable[..., ScheduledOperationRecord],
    execute_due_approved_rerun_schedules: Callable[..., list[ScheduledExecutionRecord]],
) -> None:
    @app.post('/digest-schedules', response_model=ScheduledOperationRecord, status_code=status.HTTP_201_CREATED)
    def create_digest_schedule(request: DigestScheduleCreateRequest) -> ScheduledOperationRecord:
        record = build_digest_schedule(request, settings)
        store.save_schedule(record)
        return record

    @app.get('/digest-schedules', response_model=list[ScheduledOperationRecord])
    def list_digest_schedules() -> list[ScheduledOperationRecord]:
        return store.list_schedules(operation_type='digest')

    @app.post('/digest-schedules/{schedule_id}/disable', response_model=ScheduledOperationRecord)
    def disable_digest_schedule(schedule_id: str) -> ScheduledOperationRecord:
        record = store.get_schedule(schedule_id)
        if record is None or record.operation_type != 'digest':
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='digest schedule not found')
        updated = disable_schedule(record)
        store.save_schedule(updated)
        return updated

    @app.post('/approved-rerun-schedules/from-latest-run', response_model=ScheduledOperationRecord, status_code=status.HTTP_201_CREATED)
    def create_approved_rerun_schedule_from_latest_run(
        request: ApprovedRerunScheduleCreateRequest,
    ) -> ScheduledOperationRecord:
        run = store.get_latest_run()
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        resolved_run = run.model_copy(update={'status': resolve_run_status(run, settings, submitter)})
        record = build_approved_rerun_schedule(request, resolved_run, settings)
        store.save_schedule(record)
        return record

    @app.get('/approved-rerun-schedules', response_model=list[ScheduledOperationRecord])
    def list_approved_rerun_schedules() -> list[ScheduledOperationRecord]:
        return store.list_schedules(operation_type='approved-rerun')

    @app.post('/approved-rerun-schedules/{schedule_id}/disable', response_model=ScheduledOperationRecord)
    def disable_approved_rerun_schedule(schedule_id: str) -> ScheduledOperationRecord:
        record = store.get_schedule(schedule_id)
        if record is None or record.operation_type != 'approved-rerun':
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='approved rerun schedule not found')
        updated = disable_schedule(record)
        store.save_schedule(updated)
        return updated

    @app.post('/digest-schedules/run-due', response_model=list[ScheduledExecutionRecord])
    def run_due_digest_schedules() -> list[ScheduledExecutionRecord]:
        now = datetime.now(timezone.utc)
        return execute_due_digest_schedules(store, now)

    @app.post('/approved-rerun-schedules/run-due', response_model=list[ScheduledExecutionRecord])
    def run_due_approved_rerun_schedules() -> list[ScheduledExecutionRecord]:
        now = datetime.now(timezone.utc)
        return execute_due_approved_rerun_schedules(store, now, settings, registry, submitter)

    @app.get('/scheduled-executions', response_model=list[ScheduledExecutionRecord])
    def list_scheduled_executions(schedule_id: str | None = None) -> list[ScheduledExecutionRecord]:
        return store.list_executions(schedule_id=schedule_id)
