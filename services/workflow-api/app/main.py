from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from services.common.schemas import ArtifactIndexEntry, ArtifactsIndex, RunManifest, RunStatus

from .config import Settings, get_settings
from .job_submission import JobSubmitter, NullJobSubmitter
from .persistence import InMemoryRunStore, RunStore
from .registry import WorkflowRegistry
from .schemas import (
    LogEntry,
    RunArtifactsResponse,
    RunCreateRequest,
    RunLogsResponse,
    RunRecord,
    WorkflowFamilySummary,
)
from .validation import validate_run_request

MEDIA_TYPES = {
    '.json': 'application/json',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.txt': 'text/plain',
}


def create_app(
    settings: Settings | None = None,
    registry: WorkflowRegistry | None = None,
    store: RunStore | None = None,
    submitter: JobSubmitter | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    registry = registry or WorkflowRegistry(settings.registry_dir)
    store = store or InMemoryRunStore()
    submitter = submitter or NullJobSubmitter(namespace=settings.runner_namespace)

    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.settings = settings
    app.state.registry = registry
    app.state.store = store
    app.state.submitter = submitter

    @app.get('/healthz')
    def healthz() -> dict:
        return {
            'status': 'ok',
            'app': settings.app_name,
            'version': settings.app_version,
            'workflow_count': len(registry.list_workflows()),
        }

    @app.get('/workflow-families', response_model=list[WorkflowFamilySummary])
    def list_workflow_families() -> list[WorkflowFamilySummary]:
        return [
            WorkflowFamilySummary(
                workflow_id=entry.workflow_id,
                display_name=entry.display_name,
                workflow_family=entry.workflow_family,
                description=entry.description,
                allowed_models=entry.allowed_models,
                resource_profile=entry.resource_profile.profile_name,
                approval_tier=entry.approval_tier,
            )
            for entry in registry.list_workflows()
        ]

    @app.post('/runs', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run(request: RunCreateRequest) -> RunRecord:
        workflow = registry.get_workflow(request.workflow_id)
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[{'field': 'workflow_id', 'message': f'unsupported workflow family: {request.workflow_id}'}],
            )

        issues = validate_run_request(request, workflow)
        if issues:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[issue.model_dump() for issue in issues],
            )

        now = datetime.now(timezone.utc)
        run_id = uuid4().hex
        manifest = RunManifest(
            run_id=run_id,
            workflow_id=workflow.workflow_id,
            workflow_family=workflow.workflow_family,
            display_name=workflow.display_name,
            objective=request.objective,
            submitted_by=request.submitted_by or settings.default_submitted_by,
            submitted_at=now,
            inputs=request.inputs,
            requested_models=request.models,
            resource_profile=request.resource_profile or workflow.resource_profile.profile_name,
            runner_image=workflow.runner_image,
            evaluator_type=workflow.evaluator_type,
            approval_tier=workflow.approval_tier,
            expected_artifacts=workflow.expected_artifacts.model_dump(mode='json'),
        )
        status_payload = RunStatus(run_id=run_id, status='accepted', updated_at=now, detail='Run accepted by workflow-api.')
        submission = submitter.submit_run(manifest)
        record = RunRecord(
            run_id=run_id,
            workflow_id=workflow.workflow_id,
            created_at=now,
            updated_at=now,
            manifest=manifest,
            status=status_payload,
            job_submission=submission,
        )
        artifacts = build_artifact_index(run_id, workflow.expected_artifacts.required, workflow.expected_artifacts.optional)
        store.save_run(record)
        store.save_artifacts(run_id, artifacts)
        store.append_log(
            run_id,
            LogEntry(
                timestamp=now,
                level='INFO',
                message='run accepted',
                payload={'workflow_id': workflow.workflow_id, 'job_name': submission.job_name},
            ),
        )
        return record

    @app.get('/runs/{run_id}', response_model=RunRecord)
    def get_run(run_id: str) -> RunRecord:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        return record

    @app.get('/runs/{run_id}/artifacts', response_model=RunArtifactsResponse)
    def get_run_artifacts(run_id: str) -> RunArtifactsResponse:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        artifacts = store.get_artifacts(run_id)
        if artifacts is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='artifacts not found')
        return RunArtifactsResponse(run_id=run_id, artifacts=artifacts)

    @app.get('/runs/{run_id}/logs', response_model=RunLogsResponse)
    def get_run_logs(run_id: str) -> RunLogsResponse:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        return RunLogsResponse(run_id=run_id, logs=store.get_logs(run_id))

    return app


def build_artifact_index(run_id: str, required: Iterable[str], optional: Iterable[str]) -> ArtifactsIndex:
    artifacts: list[ArtifactIndexEntry] = []
    for name, is_required in [(item, True) for item in required] + [(item, False) for item in optional]:
        path = f'runs/{run_id}/{name}'
        suffix = '' if name.endswith('/') else name[name.rfind('.'):]
        media_type = 'inode/directory' if name.endswith('/') else MEDIA_TYPES.get(suffix, 'application/octet-stream')
        artifacts.append(
            ArtifactIndexEntry(
                name=name,
                path=path,
                media_type=media_type,
                required=is_required,
                description='Declared by workflow registry',
            )
        )
    return ArtifactsIndex(run_id=run_id, artifacts=artifacts)
