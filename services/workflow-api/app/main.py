from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Iterable
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from services.common.schemas import ArtifactIndexEntry, ArtifactsIndex, RunManifest, RunStatus, WorkflowRegistryEntry

from .config import Settings, get_settings
from .autoresearch_routes import register_autoresearch_routes
from .digest_scheduling import schedule_is_due
from .execution_routes import register_execution_routes
from .execution_preflight import build_execution_preflight_result
from .external_literature import search_external_literature
from .job_submission import JobSubmitter, create_job_submitter
from .literature_routes import register_literature_routes
from .paper_pipeline import (
    auto_resolve_pipeline_design_inputs as auto_resolve_pipeline_design_inputs_impl,
    build_fresh_paper_intake_request as build_fresh_paper_intake_request_impl,
    default_paper_pipeline_request_text as default_paper_pipeline_request_text_impl,
    resolve_replication_repository_url as resolve_replication_repository_url_impl,
)
from .persistence import RunStore, create_run_store
from .registry import WorkflowRegistry
from .source_documents import build_source_fetch_candidates
from .schedule_routes import register_schedule_routes
from .source_documents import ingest_source_document, register_source_document_routes
from .stage_interpretation import (
    build_interpretation_record_from_agent_draft,
    call_interpretation_agent,
    validate_interpretation_agent_draft,
)
from .stage_design import (
    build_design_draft as build_design_draft_impl,
    build_design_draft_from_agent_draft as build_design_draft_from_agent_draft_impl,
    build_replicability_assessment as build_replicability_assessment_impl,
    build_replicability_assessment_from_agent_draft as build_replicability_assessment_from_agent_draft_impl,
    call_assessment_agent as call_assessment_agent_impl,
    call_design_agent as call_design_agent_impl,
    choose_workflow_for_intake as choose_workflow_for_intake_impl,
    derive_design_from_intake as derive_design_from_intake_impl,
    validate_assessment_agent_draft as validate_assessment_agent_draft_impl,
    validate_design_agent_draft as validate_design_agent_draft_impl,
)
from .stage_inference import (
    build_interpretation_notes,
    build_interpretation_record,
    build_intake_record_from_agent_draft,
    build_ranker_candidates,
    call_intake_agent,
    infer_bounded_experiment_ideas,
    infer_dataset_hints,
    infer_evaluation_targets,
    infer_extracted_claims,
    infer_intake_source_type,
    infer_literature_state_summary,
    infer_research_gaps,
    infer_unresolved_questions,
    infer_workflow_candidates,
    normalize_unique_strings,
    reorder_intake_candidates_with_ranker,
    resolve_intake_agent_base_url,
    summarize_intake,
    validate_intake_agent_draft,
    validate_ranker_response,
)
from .session_helpers import (
    append_research_session_memory,
    build_research_problem_request_from_session,
    build_research_session_context,
    build_research_session_literature_digest,
    build_research_session_record,
    get_required_research_session,
    get_required_session_latest_assessment,
    get_required_session_latest_design,
    get_required_session_latest_intake,
    get_required_session_latest_interpretation,
    touch_research_session,
)
from .run_artifacts import (
    MEDIA_TYPES,
    load_artifacts_from_disk,
    load_logs_from_disk,
    resolve_run_status,
)
from .schemas import (
    DesignDraftRecord,
    DesignDraftReviewRequest,
    ExecutionPreflightResult,
    FreshPaperPipelineRequest,
    FreshPaperPipelineResponse,
    IntakeCreateRequest,
    IntakeRecord,
    InterpretationRecord,
    LogEntry,
    OperationRecord,
    PaperIntakeCandidateRecord,
    PaperIntakeQueueCreateRequest,
    PaperIntakeQueueRecord,
    PaperPipelineReportState,
    ResearchProblemPaperCandidate,
    ResearchProblemRecord,
    ResearchProblemPipelineRequest,
    ResearchProblemPipelineResponse,
    ReplicabilityAssessmentRecord,
    RunArtifactsResponse,
    RunCreateRequest,
    RunLogsResponse,
    RunRecord,
    ScheduledExecutionRecord,
    ScheduledOperationRecord,
    SourceDocumentRecord,
    WorkflowFamilySummary,
)
from .validation import validate_run_request

UNRESOLVED_PREFIX = 'UNRESOLVED_'
LOGGER = logging.getLogger(__name__)


def log_stage_record_source(stage: str, source: str, record_id: str, **context: str) -> None:
    fields = [f'stage={stage}', f'source={source}', f'record_id={record_id}']
    for key in sorted(context):
        value = context[key]
        if value:
            fields.append(f'{key}={value}')
    LOGGER.info('stage-record-created %s', ' '.join(fields))


def record_operation(
    store: RunStore,
    *,
    operation_type: str,
    started_at: datetime,
    status: str,
    result_detail: str,
    session_id: str | None = None,
    queue_id: str | None = None,
    document_id: str | None = None,
    intake_id: str | None = None,
    error_detail: str | None = None,
) -> OperationRecord:
    record = OperationRecord(
        operation_id=uuid4().hex,
        operation_type=operation_type,
        status=status,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        session_id=session_id,
        queue_id=queue_id,
        document_id=document_id,
        intake_id=intake_id,
        result_detail=result_detail,
        error_detail=error_detail,
    )
    store.save_operation(record)
    return record

def build_replicability_assessment(
    interpretation: InterpretationRecord,
    registry: WorkflowRegistry,
) -> ReplicabilityAssessmentRecord:
    return build_replicability_assessment_impl(interpretation, registry)


def validate_assessment_agent_draft(
    draft: dict[str, Any],
    interpretation: InterpretationRecord,
    registry: WorkflowRegistry,
) -> dict[str, Any]:
    _ = interpretation
    return validate_assessment_agent_draft_impl(draft, registry)


def build_replicability_assessment_from_agent_draft(
    interpretation: InterpretationRecord,
    validated_draft: dict[str, Any],
) -> ReplicabilityAssessmentRecord:
    return build_replicability_assessment_from_agent_draft_impl(interpretation, validated_draft)


def call_assessment_agent(
    interpretation: InterpretationRecord,
    settings: Settings,
    registry: WorkflowRegistry,
) -> ReplicabilityAssessmentRecord | None:
    return call_assessment_agent_impl(interpretation, settings, registry)


def choose_workflow_for_intake(intake: IntakeRecord, registry: WorkflowRegistry) -> WorkflowRegistryEntry | None:
    return choose_workflow_for_intake_impl(intake, registry)


def derive_design_from_intake(intake: IntakeRecord, workflow: WorkflowRegistryEntry) -> tuple[dict[str, Any], list[str], list[str]]:
    return derive_design_from_intake_impl(intake, workflow)


def compute_unresolved_inputs(declared_inputs: dict[str, Any]) -> list[str]:
    return [
        name for name, value in declared_inputs.items() if isinstance(value, str) and value.startswith(UNRESOLVED_PREFIX)
    ]


def default_paper_pipeline_request_text(paper_ref: str) -> str:
    return default_paper_pipeline_request_text_impl(paper_ref)


def build_fresh_paper_intake_request(
    request: FreshPaperPipelineRequest,
    settings: Settings,
) -> IntakeCreateRequest:
    return build_fresh_paper_intake_request_impl(request, settings)


def resolve_replication_repository_url(intake: IntakeRecord) -> str | None:
    return resolve_replication_repository_url_impl(intake)


def auto_resolve_pipeline_design_inputs(
    design: DesignDraftRecord,
    intake: IntakeRecord,
    interpretation: InterpretationRecord,
    request: FreshPaperPipelineRequest,
) -> tuple[dict[str, Any], list[str]]:
    return auto_resolve_pipeline_design_inputs_impl(design, intake, interpretation, request)


def wait_for_terminal_run_state(
    run: RunRecord,
    settings: Settings,
    submitter: JobSubmitter,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> RunRecord:
    deadline = time.monotonic() + timeout_seconds
    current = run
    while True:
        resolved_status = resolve_run_status(current, settings, submitter)
        current = current.model_copy(update={'status': resolved_status, 'updated_at': resolved_status.updated_at})
        if resolved_status.status in {'succeeded', 'failed', 'rejected'}:
            return current
        if time.monotonic() >= deadline:
            return current
        time.sleep(poll_interval_seconds)


def build_paper_pipeline_report_state(
    run: RunRecord | None,
    settings: Settings,
    submitter: JobSubmitter,
    store: RunStore,
) -> PaperPipelineReportState:
    if run is None:
        return PaperPipelineReportState(
            run_id=None,
            run_status='not-submitted',
            terminal=False,
            report_available=False,
            report_path=None,
            artifact_count=0,
            artifact_names=[],
        )

    resolved_status = resolve_run_status(run, settings, submitter)
    artifacts = load_artifacts_from_disk(settings, run.run_id) or store.get_artifacts(run.run_id)
    artifact_names: list[str] = []
    report_path = None
    if artifacts is not None:
        artifact_names = [artifact.name for artifact in artifacts.artifacts]
        for artifact in artifacts.artifacts:
            if artifact.name == 'report.md':
                report_path = artifact.path
                break

    return PaperPipelineReportState(
        run_id=run.run_id,
        run_status=resolved_status.status,
        terminal=resolved_status.status in {'succeeded', 'failed', 'rejected'},
        report_available=report_path is not None,
        report_path=report_path,
        artifact_count=len(artifact_names),
        artifact_names=artifact_names,
    )


def validate_problem_harvester_response(payload: dict[str, Any]) -> dict[str, Any]:
    selected_tracks = payload.get('selected_tracks')
    selected_queries = payload.get('selected_queries')
    selected_papers = payload.get('selected_papers')
    if not isinstance(selected_tracks, list):
        raise ValueError('problem harvester response missing selected_tracks')
    if not isinstance(selected_queries, list):
        raise ValueError('problem harvester response missing selected_queries')
    if not isinstance(selected_papers, list):
        raise ValueError('problem harvester response missing selected_papers')
    return payload


def call_problem_harvester_plan(
    request: ResearchProblemPipelineRequest,
    settings: Settings,
) -> dict[str, Any]:
    payload = {
        'request_id': uuid4().hex,
        'problem_statement': request.problem_statement,
        'priorities': request.priorities,
        'max_papers': request.max_candidate_papers,
    }
    request_obj = urllib_request.Request(
        resolve_intake_agent_base_url(settings) + '/paper-harvester/plan-from-problem',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    with urllib_request.urlopen(request_obj, timeout=settings.intake_agent_timeout_seconds) as response:
        body = json.loads(response.read().decode('utf-8'))
    return validate_problem_harvester_response(body)


def build_fresh_paper_request_from_problem(
    request: ResearchProblemPipelineRequest,
    chosen_paper: ResearchProblemPaperCandidate,
    selected_track_ids: list[str],
) -> FreshPaperPipelineRequest:
    paper_ref = (
        next(iter(build_source_fetch_candidates(chosen_paper.official_page, chosen_paper.pdf_url)), None)
        or chosen_paper.paper_id
    )
    notes = [chosen_paper.why_seed]
    notes.extend(chosen_paper.first_jobs[:2])
    if selected_track_ids:
        notes.append('Selected tracks: ' + ', '.join(selected_track_ids))
    return FreshPaperPipelineRequest(
        paper_ref=paper_ref,
        raw_request=(
            f'Investigate this research problem with a bounded literature-derived experiment: '
            f'{request.problem_statement.strip()}'
        ),
        notes=notes,
        submitted_by=request.submitted_by,
        wait_for_terminal_state=request.wait_for_terminal_state,
        wait_timeout_seconds=request.wait_timeout_seconds,
        poll_interval_seconds=request.poll_interval_seconds,
    )


def enrich_intake_with_interpretation_context(
    intake: IntakeRecord,
    interpretation: InterpretationRecord | None,
) -> IntakeRecord:
    if interpretation is None:
        return intake
    extra_notes = list(intake.notes)
    if interpretation.literature_state_summary:
        extra_notes.append('Literature state: ' + interpretation.literature_state_summary)
    if interpretation.bounded_experiment_ideas:
        extra_notes.append('Bounded experiment ideas: ' + '; '.join(interpretation.bounded_experiment_ideas[:2]))
    if interpretation.research_gaps:
        extra_notes.append('Research gaps: ' + '; '.join(interpretation.research_gaps[:2]))
    return intake.model_copy(
        update={
            'notes': normalize_unique_strings(extra_notes),
            'updated_at': datetime.now(timezone.utc),
        }
    )


def build_research_problem_record(
    request: ResearchProblemPipelineRequest,
    settings: Settings,
    session_id: str | None = None,
) -> ResearchProblemRecord:
    now = datetime.now(timezone.utc)
    return ResearchProblemRecord(
        problem_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status='staged',
        problem_statement=request.problem_statement.strip(),
        max_candidate_papers=request.max_candidate_papers,
        priorities=request.priorities,
        submitted_by=request.submitted_by or settings.default_submitted_by,
        session_id=session_id,
    )


def build_research_problem_request_from_record(
    record: ResearchProblemRecord,
    settings: Settings,
) -> ResearchProblemPipelineRequest:
    return ResearchProblemPipelineRequest(
        problem_statement=record.problem_statement,
        max_candidate_papers=record.max_candidate_papers,
        priorities=record.priorities,
        submitted_by=record.submitted_by or settings.default_submitted_by,
    )


def build_paper_intake_queue_record(
    request: PaperIntakeQueueCreateRequest,
    selected_track_ids: list[str],
    selected_queries: list[str],
    selected_papers: list[ResearchProblemPaperCandidate],
    coverage_summary: dict[str, Any],
    warnings: list[str],
    settings: Settings,
    session_id: str | None = None,
) -> PaperIntakeQueueRecord:
    now = datetime.now(timezone.utc)
    candidates = [
        PaperIntakeCandidateRecord(**candidate.model_dump())
        for candidate in selected_papers
    ]
    status_value = 'ready' if candidates else 'exhausted'
    return PaperIntakeQueueRecord(
        queue_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status=status_value,
        problem_statement=request.problem_statement.strip(),
        selected_tracks=selected_track_ids,
        selected_queries=selected_queries,
        coverage_summary=coverage_summary,
        warnings=warnings,
        candidates=candidates,
        submitted_by=request.submitted_by or settings.default_submitted_by,
        session_id=session_id,
    )


def build_intake_request_from_problem_candidate(
    queue: PaperIntakeQueueRecord,
    candidate: PaperIntakeCandidateRecord,
    document_refs: list[str] | None = None,
    extra_notes: list[str] | None = None,
) -> IntakeCreateRequest:
    def append_unique_note(target: list[str], value: str | None) -> None:
        if not value or value in target:
            return
        target.append(value)

    paper_ref = (
        next(iter(build_source_fetch_candidates(candidate.official_page, candidate.pdf_url)), None)
        or candidate.paper_id
    )
    notes: list[str] = []
    append_unique_note(notes, candidate.why_seed)
    for note in candidate.first_jobs[:2]:
        append_unique_note(notes, note)
    if queue.selected_tracks:
        append_unique_note(notes, 'Selected tracks: ' + ', '.join(queue.selected_tracks))
    if extra_notes:
        for note in extra_notes:
            append_unique_note(notes, note)
    return IntakeCreateRequest(
        raw_request=(
            'Investigate this research problem with a bounded literature-derived experiment: '
            + queue.problem_statement.strip()
        ),
        source_refs=[paper_ref],
        document_refs=document_refs or [],
        source_type='paper-link',
        notes=notes,
        submitted_by=queue.submitted_by,
    )


def stage_intake_from_request(
    request: IntakeCreateRequest,
    settings: Settings,
    registry: WorkflowRegistry,
    store: RunStore,
    session_id: str | None = None,
) -> IntakeRecord:
    record = call_intake_agent(request, settings, registry)
    source = 'agent'
    if record is None:
        source = 'deterministic'
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
            document_refs=request.document_refs,
            raw_request=request.raw_request.strip(),
            normalized_summary=summarize_intake(request.raw_request, request.notes),
            workflow_family_candidates=candidates,
            notes=request.notes,
            submitted_by=request.submitted_by or settings.default_submitted_by,
            session_id=session_id,
        )
    elif request.document_refs:
        record = record.model_copy(
            update={
                'document_refs': normalize_unique_strings(list(record.document_refs) + list(request.document_refs)),
                'updated_at': datetime.now(timezone.utc),
                'session_id': session_id or record.session_id,
            }
        )
    elif session_id and record.session_id != session_id:
        record = record.model_copy(
            update={
                'session_id': session_id,
                'updated_at': datetime.now(timezone.utc),
            }
        )
    record = reorder_intake_candidates_with_ranker(record, settings, registry)
    store.save_intake(record)
    log_stage_record_source(
        'intake',
        source,
        record.intake_id,
        intake_id=record.intake_id,
        submitted_by=record.submitted_by,
    )
    touch_research_session(store, record.session_id, latest_intake_id=record.intake_id)
    return record


def build_design_draft(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    source_assessment_id: str | None = None,
) -> DesignDraftRecord:
    return build_design_draft_impl(
        intake,
        workflow,
        submitted_by=submitted_by,
        source_assessment_id=source_assessment_id,
    )


def validate_design_agent_draft(
    draft: dict[str, Any],
    workflow: WorkflowRegistryEntry,
) -> dict[str, Any]:
    return validate_design_agent_draft_impl(draft, workflow)


def build_design_draft_from_agent_draft(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    validated_draft: dict[str, Any],
    source_assessment_id: str | None = None,
) -> DesignDraftRecord:
    return build_design_draft_from_agent_draft_impl(
        intake,
        workflow,
        submitted_by=submitted_by,
        validated_draft=validated_draft,
        source_assessment_id=source_assessment_id,
    )


def call_design_agent(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    settings: Settings,
    source_assessment_id: str | None = None,
) -> DesignDraftRecord | None:
    return call_design_agent_impl(
        intake,
        workflow,
        submitted_by=submitted_by,
        settings=settings,
        source_assessment_id=source_assessment_id,
    )


def review_design_draft(
    design: DesignDraftRecord,
    request: DesignDraftReviewRequest,
) -> DesignDraftRecord:
    now = datetime.now(timezone.utc)
    declared_inputs = dict(design.declared_inputs)
    declared_inputs.update(request.resolved_inputs)
    unresolved_inputs = compute_unresolved_inputs(declared_inputs)
    design_notes = list(design.design_notes)

    for key in sorted(request.resolved_inputs):
        design_notes.append(f'Review resolved input: {key}.')
    design_notes.extend(request.review_notes)

    status_value = 'ready_for_run'
    if unresolved_inputs:
        status_value = 'needs_review'
    if design.approval_tier != 'tier-2-approved-execution':
        status_value = 'needs_review'
        note = f'Approval tier {design.approval_tier} still requires operator review before run creation.'
        if note not in design_notes:
            design_notes.append(note)

    return design.model_copy(
        update={
            'updated_at': now,
            'declared_inputs': declared_inputs,
            'unresolved_inputs': unresolved_inputs,
            'design_notes': design_notes,
            'status': status_value,
        }
    )


def build_approved_rerun_schedule(
    request: ApprovedRerunScheduleCreateRequest,
    run: RunRecord,
    settings: Settings,
) -> ScheduledOperationRecord:
    if run.manifest.approval_tier != 'tier-2-approved-execution':
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='latest run is not eligible for approved rerun scheduling',
        )
    if run.status.status != 'succeeded':
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='latest run must be succeeded before creating an approved rerun schedule',
        )

    dataset_uri = None
    for candidate in ('dataset_uri', 'train_uri'):
        value = run.manifest.inputs.get(candidate)
        if isinstance(value, str) and value.strip():
            dataset_uri = value.strip()
            break

    now = datetime.now(timezone.utc)
    return ScheduledOperationRecord(
        schedule_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status='active',
        operation_type='approved-rerun',
        approval_tier=run.manifest.approval_tier,
        owner=request.owner or settings.default_submitted_by,
        cron_expr=request.cron_expr.strip(),
        scope_filter={'workflow_id': run.workflow_id, 'source_run_id': run.run_id},
        source_design_id=run.source_design_id,
        source_run_id=run.run_id,
        workflow_id=run.workflow_id,
        allowed_dataset_uri=dataset_uri,
        allowed_model_ids=list(run.manifest.requested_models),
        allowed_runner_image=run.manifest.runner_image,
        resource_profile=run.manifest.resource_profile,
    )


def execute_due_approved_rerun_schedules(
    store: RunStore,
    now: datetime,
    settings: Settings,
    registry: WorkflowRegistry,
    submitter: JobSubmitter,
) -> list[ScheduledExecutionRecord]:
    executions: list[ScheduledExecutionRecord] = []
    for schedule in store.list_schedules(operation_type='approved-rerun'):
        if not schedule_is_due(schedule, now):
            continue
        if schedule.last_execution_at is not None:
            last = schedule.last_execution_at.astimezone(timezone.utc)
            if last.year == now.year and last.month == now.month and last.day == now.day and last.hour == now.hour and last.minute == now.minute:
                continue

        started_at = now
        source_run = store.get_run(schedule.source_run_id or '')
        failure_reason = None
        if source_run is None:
            failure_reason = 'source run not found'
        else:
            resolved_status = resolve_run_status(source_run, settings, submitter)
            if resolved_status != source_run.status:
                source_run = source_run.model_copy(update={'status': resolved_status, 'updated_at': resolved_status.updated_at})
                store.save_run(source_run)
        if failure_reason is None and source_run.status.status != 'succeeded':
            failure_reason = 'source run is no longer succeeded'
        elif failure_reason is None and schedule.workflow_id != source_run.workflow_id:
            failure_reason = 'scheduled workflow_id drifted from source run'
        elif failure_reason is None and schedule.resource_profile != source_run.manifest.resource_profile:
            failure_reason = 'scheduled resource profile drifted from source run'
        elif failure_reason is None and schedule.allowed_runner_image != source_run.manifest.runner_image:
            failure_reason = 'scheduled runner image drifted from source run'
        elif failure_reason is None and schedule.allowed_model_ids != list(source_run.manifest.requested_models):
            failure_reason = 'scheduled model ids drifted from source run'
        elif failure_reason is None:
            dataset_uri = None
            for candidate in ('dataset_uri', 'train_uri'):
                value = source_run.manifest.inputs.get(candidate)
                if isinstance(value, str) and value.strip():
                    dataset_uri = value.strip()
                    break
            if schedule.allowed_dataset_uri != dataset_uri:
                failure_reason = 'scheduled dataset uri drifted from source run'

        if failure_reason is not None:
            execution = ScheduledExecutionRecord(
                execution_id=uuid4().hex,
                schedule_id=schedule.schedule_id,
                operation_type=schedule.operation_type,
                started_at=started_at,
                finished_at=started_at,
                result_status='failed-closed',
                result_detail=failure_reason,
                produced_run_ids=[],
                digest_payload={},
            )
            store.save_execution(execution)
            store.save_schedule(
                schedule.model_copy(
                    update={
                        'updated_at': started_at,
                        'last_execution_at': started_at,
                        'last_result_status': 'failed-closed',
                        'last_result_detail': failure_reason,
                    }
                )
            )
            executions.append(execution)
            continue

        assert source_run is not None
        workflow = registry.get_workflow(source_run.workflow_id)
        if workflow is None:
            detail = 'workflow registry entry not found for scheduled rerun'
            execution = ScheduledExecutionRecord(
                execution_id=uuid4().hex,
                schedule_id=schedule.schedule_id,
                operation_type=schedule.operation_type,
                started_at=started_at,
                finished_at=started_at,
                result_status='failed-closed',
                result_detail=detail,
                produced_run_ids=[],
                digest_payload={},
            )
            store.save_execution(execution)
            store.save_schedule(
                schedule.model_copy(
                    update={
                        'updated_at': started_at,
                        'last_execution_at': started_at,
                        'last_result_status': 'failed-closed',
                        'last_result_detail': detail,
                    }
                )
            )
            executions.append(execution)
            continue

        rerun_request = RunCreateRequest(
            workflow_id=source_run.workflow_id,
            objective=source_run.manifest.objective,
            inputs=source_run.manifest.inputs,
            models=list(source_run.manifest.requested_models),
            resource_profile=source_run.manifest.resource_profile,
            run_priority='autonomous',
            submitted_by=schedule.owner,
        )
        rerun_record = create_run_record(
            rerun_request,
            workflow,
            settings,
            submitter,
            store,
            source_design_id=source_run.source_design_id,
            source_intake_id=source_run.source_intake_id,
            run_purpose='approved-rerun',
            session_id=source_run.session_id,
        )
        finished_at = datetime.now(timezone.utc)
        detail = f'Approved rerun submitted as {rerun_record.run_id}.'
        execution = ScheduledExecutionRecord(
            execution_id=uuid4().hex,
            schedule_id=schedule.schedule_id,
            operation_type=schedule.operation_type,
            started_at=started_at,
            finished_at=finished_at,
            result_status='ok',
            result_detail=detail,
            produced_run_ids=[rerun_record.run_id],
            digest_payload={},
        )
        store.save_execution(execution)
        store.save_schedule(
            schedule.model_copy(
                update={
                    'updated_at': finished_at,
                    'last_execution_at': finished_at,
                    'last_result_status': 'ok',
                    'last_result_detail': detail,
                }
            )
        )
        executions.append(execution)
    return executions


def create_run_record(
    request: RunCreateRequest,
    workflow: WorkflowRegistryEntry,
    settings: Settings,
    submitter: JobSubmitter,
    store: RunStore,
    source_design_id: str | None = None,
    source_intake_id: str | None = None,
    run_purpose: str | None = None,
    session_id: str | None = None,
) -> RunRecord:
    issues = validate_run_request(request, workflow)
    if issues:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[issue.model_dump() for issue in issues],
        )

    preflight = build_execution_preflight_result(workflow, settings)
    if not preflight.ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                'message': 'execution preflight failed',
                'workflow_id': workflow.workflow_id,
                'blocking_issues': preflight.blocking_issues,
                'warnings': preflight.warnings,
                'eligible_nodes': preflight.eligible_nodes,
            },
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
        run_priority=request.run_priority,
        inputs=request.inputs,
        requested_models=request.models,
        resource_profile=request.resource_profile or workflow.resource_profile.profile_name,
        resource_requests=workflow.resource_profile.requests,
        resource_limits=workflow.resource_profile.limits,
        node_selector=workflow.resource_profile.node_selector,
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
        run_priority=request.run_priority,
        session_id=session_id,
    )
    artifacts = build_artifact_index(run_id, workflow.expected_artifacts.required, workflow.expected_artifacts.optional)
    store.save_run(record)
    touch_research_session(store, session_id, latest_run_id=run_id)
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
    if store is None:
        if settings.store_backend == 'memory' and not settings.allow_inmemory_store:
            raise RuntimeError(
                'workflow-api store backend is set to memory but allow_inmemory_store=false; '
                'choose a durable backend or explicitly allow in-memory mode'
            )
        store = create_run_store(
            settings.store_backend,
            state_path=settings.store_json_path,
        )
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
            'build_source_revision': settings.build_source_revision,
            'build_source_label': settings.build_source_label,
            'workflow_count': len(registry.list_workflows()),
            'store_backend': settings.store_backend,
        }

    @app.post('/intakes', response_model=IntakeRecord, status_code=status.HTTP_201_CREATED)
    def create_intake(request: IntakeCreateRequest) -> IntakeRecord:
        return stage_intake_from_request(request, settings, registry, store)

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

    @app.get('/research-sessions/latest/intake', response_model=IntakeRecord)
    def get_latest_session_intake() -> IntakeRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_intake(session.session_id)

    @app.get('/research-sessions/{session_id}/intake', response_model=IntakeRecord)
    def get_session_intake(session_id: str) -> IntakeRecord:
        return get_required_session_latest_intake(store, session_id)

    @app.post('/interpretations/from-latest-intake', response_model=InterpretationRecord, status_code=status.HTTP_201_CREATED)
    def create_interpretation_from_latest_intake() -> InterpretationRecord:
        intake = store.get_latest_intake()
        if intake is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        return create_interpretation_for_intake(intake)

    def create_interpretation_for_intake(intake: IntakeRecord) -> InterpretationRecord:
        record = call_interpretation_agent(intake, settings, registry, store)
        source = 'agent'
        if record is None:
            source = 'deterministic'
            record = build_interpretation_record(intake, store)
        store.save_interpretation(record)
        log_stage_record_source(
            'interpretation',
            source,
            record.interpretation_id,
            intake_id=record.intake_id,
            submitted_by=record.submitted_by,
        )
        touch_research_session(
            store,
            record.session_id,
            latest_interpretation_id=record.interpretation_id,
            next_experiment_ideas=list(dict.fromkeys(record.bounded_experiment_ideas)),
        )
        return record

    @app.post('/research-sessions/{session_id}/skills/interpretation', response_model=InterpretationRecord, status_code=status.HTTP_201_CREATED)
    def apply_session_interpretation_skill(session_id: str) -> InterpretationRecord:
        if session_id == 'latest':
            session = store.get_latest_research_session()
            if session is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
            session_id = session.session_id
        intake = get_required_session_latest_intake(store, session_id)
        return create_interpretation_for_intake(intake)

    @app.post('/research-sessions/latest/skills/interpretation', response_model=InterpretationRecord, status_code=status.HTTP_201_CREATED)
    def apply_latest_session_interpretation_skill() -> InterpretationRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return apply_session_interpretation_skill(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/create-interpretation',
        response_model=InterpretationRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_create_interpretation(session_id: str) -> InterpretationRecord:
        return apply_session_interpretation_skill(session_id)

    @app.post(
        '/research-sessions/latest/transitions/create-interpretation',
        response_model=InterpretationRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_create_latest_interpretation() -> InterpretationRecord:
        return apply_latest_session_interpretation_skill()

    @app.get('/interpretations/latest', response_model=InterpretationRecord)
    def get_latest_interpretation() -> InterpretationRecord:
        record = store.get_latest_interpretation()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='interpretation not found')
        return record

    @app.get('/interpretations/{interpretation_id}', response_model=InterpretationRecord)
    def get_interpretation(interpretation_id: str) -> InterpretationRecord:
        record = store.get_interpretation(interpretation_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='interpretation not found')
        return record

    @app.get('/research-sessions/latest/interpretation', response_model=InterpretationRecord)
    def get_latest_session_interpretation() -> InterpretationRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_interpretation(session.session_id)

    @app.get('/research-sessions/{session_id}/interpretation', response_model=InterpretationRecord)
    def get_session_interpretation(session_id: str) -> InterpretationRecord:
        return get_required_session_latest_interpretation(store, session_id)

    @app.post(
        '/replicability-assessments/from-latest-interpretation',
        response_model=ReplicabilityAssessmentRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_replicability_assessment_from_latest_interpretation() -> ReplicabilityAssessmentRecord:
        interpretation = store.get_latest_interpretation()
        if interpretation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='interpretation not found')
        return create_replicability_assessment_for_interpretation(interpretation)

    def create_replicability_assessment_for_interpretation(
        interpretation: InterpretationRecord,
    ) -> ReplicabilityAssessmentRecord:
        record = call_assessment_agent(interpretation, settings, registry)
        source = 'agent'
        if record is None:
            source = 'deterministic'
            record = build_replicability_assessment(interpretation, registry)
        store.save_replicability_assessment(record)
        log_stage_record_source(
            'assessment',
            source,
            record.assessment_id,
            intake_id=record.intake_id,
            interpretation_id=record.interpretation_id,
            submitted_by=record.submitted_by,
        )
        touch_research_session(
            store,
            record.session_id,
            latest_assessment_id=record.assessment_id,
            decision_log=list(
                dict.fromkeys(
                    [
                        f'assessment recommendation: {record.recommendation}',
                        *record.blocking_reasons,
                    ]
                )
            ),
        )
        return record

    @app.post(
        '/research-sessions/{session_id}/skills/assessment',
        response_model=ReplicabilityAssessmentRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def apply_session_assessment_skill(session_id: str) -> ReplicabilityAssessmentRecord:
        interpretation = get_required_session_latest_interpretation(store, session_id)
        return create_replicability_assessment_for_interpretation(interpretation)

    @app.post(
        '/research-sessions/latest/skills/assessment',
        response_model=ReplicabilityAssessmentRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def apply_latest_session_assessment_skill() -> ReplicabilityAssessmentRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return apply_session_assessment_skill(session.session_id)

    @app.get('/replicability-assessments/latest', response_model=ReplicabilityAssessmentRecord)
    def get_latest_replicability_assessment() -> ReplicabilityAssessmentRecord:
        record = store.get_latest_replicability_assessment()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='replicability assessment not found')
        return record

    @app.get('/replicability-assessments/{assessment_id}', response_model=ReplicabilityAssessmentRecord)
    def get_replicability_assessment(assessment_id: str) -> ReplicabilityAssessmentRecord:
        record = store.get_replicability_assessment(assessment_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='replicability assessment not found')
        return record

    @app.get('/research-sessions/latest/assessment', response_model=ReplicabilityAssessmentRecord)
    def get_latest_session_assessment() -> ReplicabilityAssessmentRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_assessment(session.session_id)

    @app.get('/research-sessions/{session_id}/assessment', response_model=ReplicabilityAssessmentRecord)
    def get_session_assessment(session_id: str) -> ReplicabilityAssessmentRecord:
        return get_required_session_latest_assessment(store, session_id)

    @app.post('/design-drafts/from-latest-intake', response_model=DesignDraftRecord, status_code=status.HTTP_201_CREATED)
    def create_design_draft_from_latest_intake() -> DesignDraftRecord:
        intake = store.get_latest_intake()
        if intake is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        latest_interpretation = store.get_latest_interpretation()
        interpretation = latest_interpretation if latest_interpretation and latest_interpretation.intake_id == intake.intake_id else None
        return create_design_draft_for_intake(intake, interpretation=interpretation)

    def create_design_draft_for_intake(
        intake: IntakeRecord,
        *,
        interpretation: InterpretationRecord | None = None,
        source_assessment_id: str | None = None,
        submitted_by: str | None = None,
        workflow_id: str | None = None,
    ) -> DesignDraftRecord:
        intake_for_design = enrich_intake_with_interpretation_context(intake, interpretation)
        workflow = registry.get_workflow(workflow_id) if workflow_id else choose_workflow_for_intake(intake_for_design, registry)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='no approved workflow mapping found')
        effective_submitted_by = submitted_by or intake.submitted_by
        record = call_design_agent(
            intake_for_design,
            workflow,
            submitted_by=effective_submitted_by,
            settings=settings,
            source_assessment_id=source_assessment_id,
        )
        source = 'agent'
        if record is None:
            source = 'deterministic'
            record = build_design_draft(
                intake_for_design,
                workflow,
                submitted_by=effective_submitted_by,
                source_assessment_id=source_assessment_id,
            )
        store.save_design_draft(record)
        log_stage_record_source(
            'design',
            source,
            record.design_id,
            intake_id=record.intake_id,
            source_assessment_id=source_assessment_id,
            workflow_id=record.workflow_id,
            submitted_by=record.submitted_by,
        )
        touch_research_session(store, record.session_id, latest_design_id=record.design_id)
        return record

    @app.post('/design-drafts/from-latest-assessment', response_model=DesignDraftRecord, status_code=status.HTTP_201_CREATED)
    def create_design_draft_from_latest_assessment() -> DesignDraftRecord:
        assessment = store.get_latest_replicability_assessment()
        if assessment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='replicability assessment not found')
        if assessment.status != 'ready_for_design' or assessment.recommendation != 'proceed':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='replicability assessment is not ready_for_design')
        if not assessment.recommended_workflow_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='replicability assessment has no recommended workflow')
        intake = store.get_intake(assessment.intake_id)
        if intake is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        interpretation = store.get_interpretation(assessment.interpretation_id)
        return create_design_draft_for_intake(
            intake,
            interpretation=interpretation,
            source_assessment_id=assessment.assessment_id,
            submitted_by=assessment.submitted_by,
            workflow_id=assessment.recommended_workflow_id,
        )

    @app.post('/research-sessions/{session_id}/skills/design', response_model=DesignDraftRecord, status_code=status.HTTP_201_CREATED)
    def apply_session_design_skill(session_id: str) -> DesignDraftRecord:
        session = get_required_research_session(store, session_id)
        assessment = store.get_replicability_assessment(session.latest_assessment_id or '')
        if assessment is not None:
            if assessment.status == 'ready_for_design' and assessment.recommendation == 'proceed':
                if not assessment.recommended_workflow_id:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='research session assessment has no recommended workflow')
                intake = store.get_intake(assessment.intake_id)
                if intake is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
                interpretation = store.get_interpretation(assessment.interpretation_id)
                return create_design_draft_for_intake(
                    intake,
                    interpretation=interpretation,
                    source_assessment_id=assessment.assessment_id,
                    submitted_by=assessment.submitted_by,
                    workflow_id=assessment.recommended_workflow_id,
                )
        intake = get_required_session_latest_intake(store, session_id)
        interpretation = store.get_interpretation(session.latest_interpretation_id or '')
        if interpretation is not None and interpretation.intake_id != intake.intake_id:
            interpretation = None
        return create_design_draft_for_intake(intake, interpretation=interpretation)

    @app.post('/research-sessions/latest/skills/design', response_model=DesignDraftRecord, status_code=status.HTTP_201_CREATED)
    def apply_latest_session_design_skill() -> DesignDraftRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return apply_session_design_skill(session.session_id)

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

    @app.get('/research-sessions/latest/design', response_model=DesignDraftRecord)
    def get_latest_session_design() -> DesignDraftRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_design(session.session_id)

    @app.get('/research-sessions/{session_id}/design', response_model=DesignDraftRecord)
    def get_session_design(session_id: str) -> DesignDraftRecord:
        return get_required_session_latest_design(store, session_id)

    @app.post('/design-drafts/latest/review', response_model=DesignDraftRecord)
    def review_latest_design_draft(request: DesignDraftReviewRequest) -> DesignDraftRecord:
        record = store.get_latest_design_draft()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        updated = review_design_draft(record, request)
        store.save_design_draft(updated)
        touch_research_session(store, updated.session_id, latest_design_id=updated.design_id)
        return updated

    @app.post('/design-drafts/{design_id}/review', response_model=DesignDraftRecord)
    def review_existing_design_draft(design_id: str, request: DesignDraftReviewRequest) -> DesignDraftRecord:
        record = store.get_design_draft(design_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        updated = review_design_draft(record, request)
        store.save_design_draft(updated)
        return updated

    @app.post('/paper-pipelines/fresh-paper', response_model=FreshPaperPipelineResponse, status_code=status.HTTP_201_CREATED)
    def create_fresh_paper_pipeline(request: FreshPaperPipelineRequest) -> FreshPaperPipelineResponse:
        warnings: list[str] = []

        intake_request = build_fresh_paper_intake_request(request, settings)
        intake = call_intake_agent(intake_request, settings, registry)
        intake_source = 'agent'
        if intake is None:
            intake_source = 'deterministic'
            now = datetime.now(timezone.utc)
            candidates = [
                workflow_id
                for workflow_id in infer_workflow_candidates(intake_request.raw_request)
                if registry.get_workflow(workflow_id) is not None
            ]
            intake = IntakeRecord(
                intake_id=uuid4().hex,
                created_at=now,
                updated_at=now,
                status='ready_for_design',
                source_type=infer_intake_source_type(intake_request),
                source_refs=intake_request.source_refs,
                raw_request=intake_request.raw_request.strip(),
                normalized_summary=summarize_intake(intake_request.raw_request, intake_request.notes),
                workflow_family_candidates=candidates,
                notes=intake_request.notes,
                submitted_by=intake_request.submitted_by or settings.default_submitted_by,
            )
        intake = reorder_intake_candidates_with_ranker(intake, settings, registry)
        store.save_intake(intake)
        log_stage_record_source(
            'intake',
            intake_source,
            intake.intake_id,
            intake_id=intake.intake_id,
            submitted_by=intake.submitted_by,
        )

        interpretation = call_interpretation_agent(intake, settings, registry, store)
        interpretation_source = 'agent'
        if interpretation is None:
            interpretation_source = 'deterministic'
            interpretation = build_interpretation_record(intake, store)
        store.save_interpretation(interpretation)
        log_stage_record_source(
            'interpretation',
            interpretation_source,
            interpretation.interpretation_id,
            intake_id=interpretation.intake_id,
            submitted_by=interpretation.submitted_by,
        )

        assessment = call_assessment_agent(interpretation, settings, registry)
        assessment_source = 'agent'
        if assessment is None:
            assessment_source = 'deterministic'
            assessment = build_replicability_assessment(interpretation, registry)
        store.save_replicability_assessment(assessment)
        log_stage_record_source(
            'assessment',
            assessment_source,
            assessment.assessment_id,
            intake_id=assessment.intake_id,
            interpretation_id=assessment.interpretation_id,
            submitted_by=assessment.submitted_by,
        )

        workflow = None
        if assessment.recommended_workflow_id:
            workflow = registry.get_workflow(assessment.recommended_workflow_id)
        if workflow is None:
            workflow = choose_workflow_for_intake(intake, registry)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='no approved workflow mapping found')

        design = call_design_agent(
            intake,
            workflow,
            submitted_by=assessment.submitted_by,
            settings=settings,
            source_assessment_id=assessment.assessment_id,
        )
        design_source = 'agent'
        if design is None:
            design_source = 'deterministic'
            design = build_design_draft(
                intake,
                workflow,
                submitted_by=assessment.submitted_by,
                source_assessment_id=assessment.assessment_id,
            )

        resolved_inputs, review_notes = auto_resolve_pipeline_design_inputs(design, intake, interpretation, request)
        if resolved_inputs:
            design = review_design_draft(
                design,
                DesignDraftReviewRequest(
                    resolved_inputs=resolved_inputs,
                    review_notes=review_notes,
                ),
            )
            warnings.extend(review_notes)
        store.save_design_draft(design)
        log_stage_record_source(
            'design',
            design_source,
            design.design_id,
            intake_id=design.intake_id,
            source_assessment_id=assessment.assessment_id,
            workflow_id=design.workflow_id,
            submitted_by=design.submitted_by,
        )

        if design.status != 'ready_for_run':
            if design.unresolved_inputs:
                warnings.append('design still has unresolved inputs after bounded auto-review')
            report_state = build_paper_pipeline_report_state(None, settings, submitter, store)
            return FreshPaperPipelineResponse(
                intake=intake,
                interpretation=interpretation,
                assessment=assessment,
                design=design,
                run=None,
                report_state=report_state,
                warnings=warnings,
                next_action='review-required',
            )

        run_request = RunCreateRequest(
            workflow_id=design.workflow_id,
            objective=design.objective,
            inputs=design.declared_inputs,
            models=design.candidate_models or workflow.allowed_models[:1],
            resource_profile=design.resource_profile,
            submitted_by=design.submitted_by,
        )
        run = create_run_record(
            run_request,
            workflow,
            settings,
            submitter,
            store,
            source_design_id=design.design_id,
            source_intake_id=design.intake_id,
            run_purpose='paper-pipeline',
            session_id=design.session_id,
        )
        if request.wait_for_terminal_state:
            run = wait_for_terminal_run_state(
                run,
                settings,
                submitter,
                timeout_seconds=request.wait_timeout_seconds,
                poll_interval_seconds=request.poll_interval_seconds,
            )
            store.save_run(run)

        report_state = build_paper_pipeline_report_state(run, settings, submitter, store)
        next_action = 'await-run-completion'
        if report_state.terminal and report_state.report_available:
            next_action = 'report-ready'
        elif report_state.terminal:
            next_action = 'inspect-run-state'

        return FreshPaperPipelineResponse(
            intake=intake,
            interpretation=interpretation,
            assessment=assessment,
            design=design,
            run=run,
            report_state=report_state,
            warnings=warnings,
            next_action=next_action,
        )

    register_literature_routes(
        app,
        settings=settings,
        registry=registry,
        store=store,
        create_fresh_paper_pipeline=lambda *args, **kwargs: create_fresh_paper_pipeline(*args, **kwargs),
        call_problem_harvester_plan=lambda *args, **kwargs: call_problem_harvester_plan(*args, **kwargs),
        build_fresh_paper_request_from_problem=lambda *args, **kwargs: build_fresh_paper_request_from_problem(*args, **kwargs),
        build_research_session_record=lambda *args, **kwargs: build_research_session_record(*args, **kwargs),
        build_research_session_context=lambda *args, **kwargs: build_research_session_context(*args, **kwargs),
        build_research_session_literature_digest=lambda *args, **kwargs: build_research_session_literature_digest(*args, **kwargs),
        append_research_session_memory=lambda *args, **kwargs: append_research_session_memory(*args, **kwargs),
        build_research_problem_request_from_session=lambda *args, **kwargs: build_research_problem_request_from_session(*args, **kwargs),
        build_research_problem_record=lambda *args, **kwargs: build_research_problem_record(*args, **kwargs),
        build_research_problem_request_from_record=lambda *args, **kwargs: build_research_problem_request_from_record(*args, **kwargs),
        touch_research_session=lambda *args, **kwargs: touch_research_session(*args, **kwargs),
        build_paper_intake_queue_record=lambda *args, **kwargs: build_paper_intake_queue_record(*args, **kwargs),
        ingest_source_document=lambda *args, **kwargs: ingest_source_document(*args, **kwargs),
        build_intake_request_from_problem_candidate=lambda *args, **kwargs: build_intake_request_from_problem_candidate(*args, **kwargs),
        stage_intake_from_request=lambda *args, **kwargs: stage_intake_from_request(*args, **kwargs),
        record_operation=lambda *args, **kwargs: record_operation(*args, **kwargs),
        search_external_literature=lambda *args, **kwargs: search_external_literature(*args, **kwargs),
    )

    register_source_document_routes(app, store=store)

    @app.get('/operations', response_model=list[OperationRecord])
    def list_operations(operation_type: str | None = None) -> list[OperationRecord]:
        return store.list_operations(operation_type=operation_type)

    @app.get('/operations/latest', response_model=OperationRecord)
    def get_latest_operation() -> OperationRecord:
        record = store.get_latest_operation()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='operation not found')
        return record

    @app.get('/operations/{operation_id}', response_model=OperationRecord)
    def get_operation(operation_id: str) -> OperationRecord:
        record = store.get_operation(operation_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='operation not found')
        return record

    register_execution_routes(
        app,
        settings=settings,
        registry=registry,
        store=store,
        submitter=submitter,
        create_run_record=lambda *args, **kwargs: create_run_record(*args, **kwargs),
    )
    register_autoresearch_routes(
        app,
        settings=settings,
        registry=registry,
        store=store,
        submitter=submitter,
        create_run_record=lambda *args, **kwargs: create_run_record(*args, **kwargs),
        record_operation=lambda *args, **kwargs: record_operation(*args, **kwargs),
    )
    register_schedule_routes(
        app,
        settings=settings,
        registry=registry,
        store=store,
        submitter=submitter,
        build_approved_rerun_schedule=lambda *args, **kwargs: build_approved_rerun_schedule(*args, **kwargs),
        execute_due_approved_rerun_schedules=lambda *args, **kwargs: execute_due_approved_rerun_schedules(*args, **kwargs),
    )

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
