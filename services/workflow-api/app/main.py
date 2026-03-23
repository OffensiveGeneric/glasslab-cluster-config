from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from services.common.schemas import ArtifactIndexEntry, ArtifactsIndex, RunManifest, RunStatus, WorkflowRegistryEntry

from .config import Settings, get_settings
from .job_submission import JobSubmitter, create_job_submitter
from .persistence import InMemoryRunStore, RunStore
from .registry import WorkflowRegistry
from .schemas import (
    DesignDraftRecord,
    IntakeCreateRequest,
    IntakeRecord,
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

UNRESOLVED_PREFIX = 'UNRESOLVED_'


def summarize_intake(raw_request: str, notes: list[str]) -> str:
    summary = ' '.join(raw_request.split())
    if notes:
        note_preview = '; '.join(' '.join(item.split()) for item in notes[:2])
        summary = f'{summary} Notes: {note_preview}'
    return summary[:500]


def infer_intake_source_type(request: IntakeCreateRequest) -> str:
    if request.source_type:
        return request.source_type.strip()
    if any(ref.startswith(('http://', 'https://')) for ref in request.source_refs):
        return 'paper-link'
    lowered = request.raw_request.lower()
    if 'http://' in lowered or 'https://' in lowered:
        return 'paper-link'
    if 'paper' in lowered or 'arxiv' in lowered:
        return 'paper-note'
    return 'plain-goal'


def infer_workflow_candidates(raw_request: str) -> list[str]:
    lowered = raw_request.lower()
    matches: list[str] = []
    if any(token in lowered for token in ('replicate', 'replication', 'reproduce', 're-run')):
        matches.append('replication-lite')
    if any(token in lowered for token in ('paper', 'notes', 'literature', 'method', 'study')):
        matches.append('literature-to-experiment')
    if any(token in lowered for token in ('benchmark', 'tabular', 'dataset', 'csv', 'baseline', 'titanic')):
        matches.append('generic-tabular-benchmark')
    if not matches:
        matches.append('literature-to-experiment')
    return list(dict.fromkeys(matches))


def choose_workflow_for_intake(intake: IntakeRecord, registry: WorkflowRegistry) -> WorkflowRegistryEntry | None:
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    candidate_ids = list(intake.workflow_family_candidates)

    if 'titanic' in lowered and 'generic-tabular-benchmark' in candidate_ids:
        candidate_ids = ['generic-tabular-benchmark', *[item for item in candidate_ids if item != 'generic-tabular-benchmark']]

    for workflow_id in candidate_ids:
        workflow = registry.get_workflow(workflow_id)
        if workflow is not None:
            return workflow
    return None


def derive_design_from_intake(intake: IntakeRecord, workflow: WorkflowRegistryEntry) -> tuple[dict[str, Any], list[str], list[str]]:
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    declared_inputs: dict[str, Any] = {}
    design_notes: list[str] = []

    if workflow.workflow_id == 'generic-tabular-benchmark':
        if 'titanic' in lowered:
            declared_inputs = {
                'dataset_name': 'titanic',
                'train_uri': 's3://datasets/titanic/train.csv',
                'test_uri': 's3://datasets/titanic/test.csv',
                'target_column': 'Survived',
            }
            design_notes.append('Resolved approved Titanic benchmark inputs deterministically.')
        else:
            declared_inputs = {
                'dataset_name': 'UNRESOLVED_DATASET_NAME',
                'train_uri': 'UNRESOLVED_TRAIN_URI',
                'test_uri': 'UNRESOLVED_TEST_URI',
                'target_column': 'UNRESOLVED_TARGET_COLUMN',
            }
            design_notes.append('Dataset-specific benchmark inputs still require operator review.')
    elif workflow.workflow_id == 'literature-to-experiment':
        paper_id = intake.source_refs[0] if intake.source_refs else 'UNRESOLVED_PAPER_ID'
        source_notes = '\n'.join(intake.notes).strip() or intake.normalized_summary
        declared_inputs = {
            'paper_id': paper_id,
            'source_notes': source_notes,
            'dataset_uri': 'UNRESOLVED_DATASET_URI',
        }
        design_notes.append('Source paper metadata was normalized from the intake record.')
        design_notes.append('Dataset selection remains unresolved for literature-derived experiments.')
    else:
        paper_id = intake.source_refs[0] if intake.source_refs else 'UNRESOLVED_PAPER_ID'
        declared_inputs = {
            'paper_id': paper_id,
            'repository_url': 'UNRESOLVED_REPOSITORY_URL',
            'dataset_uri': 'UNRESOLVED_DATASET_URI',
            'evaluation_target': 'UNRESOLVED_EVALUATION_TARGET',
        }
        design_notes.append('Replication targets require explicit repository and evaluation inputs.')

    unresolved_inputs = [
        name for name, value in declared_inputs.items() if isinstance(value, str) and value.startswith(UNRESOLVED_PREFIX)
    ]
    return declared_inputs, unresolved_inputs, design_notes


def build_design_draft(intake: IntakeRecord, workflow: WorkflowRegistryEntry, submitted_by: str) -> DesignDraftRecord:
    now = datetime.now(timezone.utc)
    design_id = uuid4().hex
    declared_inputs, unresolved_inputs, design_notes = derive_design_from_intake(intake, workflow)
    candidate_models = workflow.allowed_models[:2]
    status_value = 'ready_for_run'
    if unresolved_inputs:
        status_value = 'needs_review'
    if workflow.approval_tier != 'tier-2-approved-execution':
        status_value = 'needs_review'
        design_notes.append(f'Approval tier {workflow.approval_tier} requires operator review before run creation.')

    objective = f'Derived from intake: {intake.normalized_summary}'[:500]

    return DesignDraftRecord(
        design_id=design_id,
        intake_id=intake.intake_id,
        created_at=now,
        updated_at=now,
        status=status_value,
        workflow_id=workflow.workflow_id,
        workflow_family=workflow.workflow_family,
        objective=objective,
        declared_inputs=declared_inputs,
        unresolved_inputs=unresolved_inputs,
        candidate_models=candidate_models,
        resource_profile=workflow.resource_profile.profile_name,
        expected_artifacts=workflow.expected_artifacts.model_dump(mode='json'),
        approval_tier=workflow.approval_tier,
        design_notes=design_notes,
        submitted_by=submitted_by,
    )


def create_run_record(
    request: RunCreateRequest,
    workflow: WorkflowRegistryEntry,
    settings: Settings,
    submitter: JobSubmitter,
    store: RunStore,
    source_design_id: str | None = None,
    source_intake_id: str | None = None,
    run_purpose: str | None = None,
) -> RunRecord:
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
        source_design_id=source_design_id,
        source_intake_id=source_intake_id,
        run_purpose=run_purpose,
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


def create_app(
    settings: Settings | None = None,
    registry: WorkflowRegistry | None = None,
    store: RunStore | None = None,
    submitter: JobSubmitter | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    registry = registry or WorkflowRegistry(settings.registry_dir)
    store = store or InMemoryRunStore()
    submitter = submitter or create_job_submitter(settings)

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

    @app.post('/intakes', response_model=IntakeRecord, status_code=status.HTTP_201_CREATED)
    def create_intake(request: IntakeCreateRequest) -> IntakeRecord:
        now = datetime.now(timezone.utc)
        intake_id = uuid4().hex
        candidates = [
            workflow_id
            for workflow_id in infer_workflow_candidates(request.raw_request)
            if registry.get_workflow(workflow_id) is not None
        ]
        record = IntakeRecord(
            intake_id=intake_id,
            created_at=now,
            updated_at=now,
            status='ready_for_design',
            source_type=infer_intake_source_type(request),
            source_refs=request.source_refs,
            raw_request=request.raw_request.strip(),
            normalized_summary=summarize_intake(request.raw_request, request.notes),
            workflow_family_candidates=candidates,
            notes=request.notes,
            submitted_by=request.submitted_by or settings.default_submitted_by,
        )
        store.save_intake(record)
        return record

    @app.get('/intakes/latest', response_model=IntakeRecord)
    def get_latest_intake() -> IntakeRecord:
        record = store.get_latest_intake()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        return record

    @app.get('/intakes/{intake_id}', response_model=IntakeRecord)
    def get_intake(intake_id: str) -> IntakeRecord:
        record = store.get_intake(intake_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        return record

    @app.post('/design-drafts/from-latest-intake', response_model=DesignDraftRecord, status_code=status.HTTP_201_CREATED)
    def create_design_draft_from_latest_intake() -> DesignDraftRecord:
        intake = store.get_latest_intake()
        if intake is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        workflow = choose_workflow_for_intake(intake, registry)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='no approved workflow mapping found')
        record = build_design_draft(intake, workflow, submitted_by=intake.submitted_by)
        store.save_design_draft(record)
        return record

    @app.get('/design-drafts/latest', response_model=DesignDraftRecord)
    def get_latest_design_draft() -> DesignDraftRecord:
        record = store.get_latest_design_draft()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        return record

    @app.get('/design-drafts/{design_id}', response_model=DesignDraftRecord)
    def get_design_draft(design_id: str) -> DesignDraftRecord:
        record = store.get_design_draft(design_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        return record

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
        return create_run_record(request, workflow, settings, submitter, store)

    @app.post('/runs/from-latest-design-draft', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run_from_latest_design_draft() -> RunRecord:
        design = store.get_latest_design_draft()
        if design is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        if design.status != 'ready_for_run':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='design draft is not ready_for_run')
        workflow = registry.get_workflow(design.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        request = RunCreateRequest(
            workflow_id=design.workflow_id,
            objective=design.objective,
            inputs=design.declared_inputs,
            models=design.candidate_models or workflow.allowed_models[:1],
            resource_profile=design.resource_profile,
            submitted_by=design.submitted_by,
        )
        return create_run_record(
            request,
            workflow,
            settings,
            submitter,
            store,
            source_design_id=design.design_id,
            source_intake_id=design.intake_id,
            run_purpose='validation',
        )

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
