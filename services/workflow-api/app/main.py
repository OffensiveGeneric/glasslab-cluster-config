from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import hashlib
import html
import json
import logging
import mimetypes
import re
import time
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from services.common.schemas import ArtifactIndexEntry, ArtifactsIndex, RunManifest, RunStatus, WorkflowRegistryEntry

from .config import Settings, get_settings
from .digest_scheduling import build_digest_schedule, disable_schedule, execute_due_digest_schedules, schedule_is_due
from .execution_preflight import build_execution_preflight_result
from .job_submission import JobSubmitter, create_job_submitter
from .literature_routes import register_literature_routes
from .persistence import RunStore, create_run_store
from .registry import WorkflowRegistry
from .run_artifacts import (
    MEDIA_TYPES,
    load_artifacts_from_disk,
    load_logs_from_disk,
    resolve_run_status,
)
from .schemas import (
    DesignDraftRecord,
    DesignDraftReviewRequest,
    DigestScheduleCreateRequest,
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
    ResearchSessionContextResponse,
    ResearchSessionCreateRequest,
    ResearchSessionRecord,
    ResearchProblemPaperCandidate,
    ResearchProblemRecord,
    ResearchProblemPipelineRequest,
    ResearchProblemPipelineResponse,
    ApprovedRerunScheduleCreateRequest,
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
HTML_TAG_RE = re.compile(r'<[^>]+>')
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


def summarize_session_title(title: str | None, goal_statement: str) -> str:
    if title and title.strip():
        return ' '.join(title.split())[:120]
    words = goal_statement.split()
    if len(words) <= 12:
        return ' '.join(words)[:120]
    return (' '.join(words[:12]) + '...')[:120]


def build_research_session_record(
    request: ResearchSessionCreateRequest,
    settings: Settings,
) -> ResearchSessionRecord:
    now = datetime.now(timezone.utc)
    return ResearchSessionRecord(
        session_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status='active',
        title=summarize_session_title(request.title, request.goal_statement.strip()),
        goal_statement=request.goal_statement.strip(),
        priorities=request.priorities,
        submitted_by=request.submitted_by or settings.default_submitted_by,
    )


def touch_research_session(
    store: RunStore,
    session_id: str | None,
    **updates: str | None,
) -> ResearchSessionRecord | None:
    if not session_id:
        return None
    session = store.get_research_session(session_id)
    if session is None:
        return None
    normalized_updates = {key: value for key, value in updates.items() if value}
    if not normalized_updates:
        return session
    updated = session.model_copy(
        update={
            **normalized_updates,
            'updated_at': datetime.now(timezone.utc),
        }
    )
    store.save_research_session(updated)
    return updated


def build_research_session_context(
    session: ResearchSessionRecord,
    store: RunStore,
) -> ResearchSessionContextResponse:
    return ResearchSessionContextResponse(
        session=session,
        research_problem=store.get_research_problem(session.latest_problem_id) if session.latest_problem_id else None,
        paper_intake_queue=store.get_paper_intake_queue(session.latest_queue_id) if session.latest_queue_id else None,
        source_document=store.get_source_document(session.latest_document_id) if session.latest_document_id else None,
        intake=store.get_intake(session.latest_intake_id) if session.latest_intake_id else None,
        interpretation=store.get_interpretation(session.latest_interpretation_id) if session.latest_interpretation_id else None,
        assessment=store.get_replicability_assessment(session.latest_assessment_id) if session.latest_assessment_id else None,
        design=store.get_design_draft(session.latest_design_id) if session.latest_design_id else None,
        run=store.get_run(session.latest_run_id) if session.latest_run_id else None,
    )


def get_required_research_session(store: RunStore, session_id: str) -> ResearchSessionRecord:
    session = store.get_research_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session not found')
    return session


def get_required_session_latest_intake(store: RunStore, session_id: str) -> IntakeRecord:
    session = get_required_research_session(store, session_id)
    intake = store.get_intake(session.latest_intake_id or '')
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no staged intake yet')
    return intake


def get_required_session_latest_interpretation(store: RunStore, session_id: str) -> InterpretationRecord:
    session = get_required_research_session(store, session_id)
    interpretation = store.get_interpretation(session.latest_interpretation_id or '')
    if interpretation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no interpretation yet')
    return interpretation


def get_required_session_latest_assessment(store: RunStore, session_id: str) -> ReplicabilityAssessmentRecord:
    session = get_required_research_session(store, session_id)
    assessment = store.get_replicability_assessment(session.latest_assessment_id or '')
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no assessment yet')
    return assessment


def get_required_session_latest_design(store: RunStore, session_id: str) -> DesignDraftRecord:
    session = get_required_research_session(store, session_id)
    design = store.get_design_draft(session.latest_design_id or '')
    if design is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no design draft yet')
    return design


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


def validate_intake_agent_draft(
    draft: dict[str, Any],
    registry: WorkflowRegistry,
) -> dict[str, Any]:
    required_string_fields = ('source_type', 'raw_request', 'normalized_summary', 'submitted_by')
    for field_name in required_string_fields:
        value = draft.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'intake agent draft missing valid {field_name}')

    normalized = {
        'source_type': draft['source_type'].strip(),
        'source_refs': normalize_unique_strings(list(draft.get('source_refs', []))),
        'document_refs': normalize_unique_strings(list(draft.get('document_refs', []))),
        'raw_request': draft['raw_request'].strip(),
        'normalized_summary': ' '.join(draft['normalized_summary'].split())[:500],
        'workflow_family_candidates': normalize_unique_strings(list(draft.get('workflow_family_candidates', []))),
        'notes': normalize_unique_strings(list(draft.get('notes', []))),
        'submitted_by': draft['submitted_by'].strip(),
    }

    invalid_workflows = [
        workflow_id for workflow_id in normalized['workflow_family_candidates']
        if registry.get_workflow(workflow_id) is None
    ]
    if invalid_workflows:
        raise ValueError(f'intake agent returned unapproved workflow ids: {", ".join(invalid_workflows)}')

    return normalized


def build_intake_record_from_agent_draft(
    validated_draft: dict[str, Any],
) -> IntakeRecord:
    now = datetime.now(timezone.utc)
    return IntakeRecord(
        intake_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status='ready_for_design',
        source_type=validated_draft['source_type'],
        source_refs=validated_draft['source_refs'],
        document_refs=validated_draft.get('document_refs', []),
        raw_request=validated_draft['raw_request'],
        normalized_summary=validated_draft['normalized_summary'],
        workflow_family_candidates=validated_draft['workflow_family_candidates'],
        notes=validated_draft['notes'],
        submitted_by=validated_draft['submitted_by'],
    )


def validate_ranker_response(
    payload: dict[str, Any],
    offered_workflow_ids: list[str],
) -> list[dict[str, Any]]:
    ranked_candidates = payload.get('ranked_candidates')
    if not isinstance(ranked_candidates, list) or not ranked_candidates:
        raise ValueError('ranker response missing ranked_candidates')

    offered_set = set(offered_workflow_ids)
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ranked_candidates:
        if not isinstance(item, dict):
            raise ValueError('ranker candidate must be an object')
        workflow_id = item.get('workflow_id')
        score = item.get('score')
        reason = item.get('reason')
        if not isinstance(workflow_id, str) or workflow_id not in offered_set:
            raise ValueError(f'ranker returned unexpected workflow id: {workflow_id!r}')
        if workflow_id in seen:
            raise ValueError(f'ranker returned duplicate workflow id: {workflow_id}')
        if not isinstance(score, (int, float)):
            raise ValueError(f'ranker returned non-numeric score for {workflow_id}')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f'ranker returned empty reason for {workflow_id}')
        seen.add(workflow_id)
        validated.append(
            {
                'workflow_id': workflow_id,
                'score': float(score),
                'reason': reason.strip(),
            }
        )

    if seen != offered_set:
        raise ValueError('ranker response does not cover the offered workflow set exactly')
    return validated


def build_ranker_candidates(
    workflow_ids: list[str],
    registry: WorkflowRegistry,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for workflow_id in workflow_ids:
        workflow = registry.get_workflow(workflow_id)
        if workflow is None:
            continue
        candidates.append(
            {
                'workflow_id': workflow.workflow_id,
                'summary': ' '.join(
                    [
                        workflow.display_name,
                        workflow.workflow_family,
                        workflow.description,
                        workflow.resource_profile.profile_name,
                        workflow.approval_tier,
                    ]
                ),
                'metadata': {
                    'resource_profile': workflow.resource_profile.profile_name,
                    'approval_tier': workflow.approval_tier,
                },
            }
        )
    return candidates


def reorder_intake_candidates_with_ranker(
    record: IntakeRecord,
    settings: Settings,
    registry: WorkflowRegistry,
) -> IntakeRecord:
    if not settings.ranker_enabled or len(record.workflow_family_candidates) < 2:
        return record

    candidates = build_ranker_candidates(record.workflow_family_candidates, registry)
    if len(candidates) < 2:
        return record

    payload = {
        'request_id': record.intake_id,
        'query': record.raw_request,
        'candidates': candidates,
        'hints': {
            'source_type': record.source_type,
            'source_refs': record.source_refs,
            'submitted_by': record.submitted_by,
        },
    }
    request_obj = urllib_request.Request(
        settings.ranker_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=settings.ranker_timeout_seconds) as response:
            response_payload = json.loads(response.read().decode('utf-8'))
        ranked_candidates = validate_ranker_response(response_payload, record.workflow_family_candidates)
        top_score = ranked_candidates[0]['score']
        second_score = ranked_candidates[1]['score'] if len(ranked_candidates) > 1 else 0.0
        score_gap = top_score - second_score
        if top_score < settings.ranker_min_top_score:
            LOGGER.info(
                'ranker-intake-order ignored intake_id=%s reason=top-score-below-threshold top_score=%.3f threshold=%.3f',
                record.intake_id,
                top_score,
                settings.ranker_min_top_score,
            )
            return record
        if score_gap < settings.ranker_min_score_gap:
            LOGGER.info(
                'ranker-intake-order ignored intake_id=%s reason=score-gap-below-threshold gap=%.3f threshold=%.3f',
                record.intake_id,
                score_gap,
                settings.ranker_min_score_gap,
            )
            return record
        reordered = [item['workflow_id'] for item in ranked_candidates]
        LOGGER.info(
            'ranker-intake-order accepted intake_id=%s reordered_candidates=%s top_score=%.3f score_gap=%.3f',
            record.intake_id,
            ','.join(reordered),
            top_score,
            score_gap,
        )
        return record.model_copy(
            update={
                'workflow_family_candidates': reordered,
                'updated_at': datetime.now(timezone.utc),
            }
        )
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning('ranker-intake-order fallback intake_id=%s reason=%s', record.intake_id, exc)
        return record


def call_intake_agent(
    request: IntakeCreateRequest,
    settings: Settings,
    registry: WorkflowRegistry,
) -> IntakeRecord | None:
    if not settings.intake_agent_enabled:
        return None

    payload = {
        'request_id': uuid4().hex,
        'intake': {
            'raw_request': request.raw_request,
            'source_refs': request.source_refs,
            'source_type': request.source_type,
            'notes': request.notes,
            'submitted_by': request.submitted_by or settings.default_submitted_by,
        },
    }
    intake_agent_endpoint = settings.intake_agent_url
    request_obj = urllib_request.Request(
        intake_agent_endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=settings.intake_agent_timeout_seconds) as response:
            body = json.loads(response.read().decode('utf-8'))
        draft = body.get('draft')
        if not isinstance(draft, dict):
            raise ValueError('intake agent response missing draft object')
        validated_draft = validate_intake_agent_draft(draft, registry)
        return build_intake_record_from_agent_draft(validated_draft)
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning('intake-agent fallback: %s', exc)
        return None


def resolve_intake_agent_base_url(settings: Settings) -> str:
    endpoint = settings.intake_agent_url.rstrip('/')
    if endpoint.endswith('/normalize-intake'):
        return endpoint[: -len('/normalize-intake')]
    return endpoint


def infer_dataset_hints(intake: IntakeRecord) -> list[str]:
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    hints: list[str] = []
    if 'titanic' in lowered:
        hints.append('titanic')
    if 'csv' in lowered:
        hints.append('csv-backed dataset')
    if 'tabular' in lowered:
        hints.append('tabular dataset')
    return list(dict.fromkeys(hints))


def infer_evaluation_targets(intake: IntakeRecord) -> list[str]:
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes]).lower()
    targets: list[str] = []
    if any(token in lowered for token in ('baseline', 'benchmark', 'compare')):
        targets.append('baseline comparison')
    if any(token in lowered for token in ('accuracy', 'auc', 'metric')):
        targets.append('reported metrics')
    if 'survived' in lowered:
        targets.append('Survived prediction target')
    if not targets and 'paper' in lowered:
        targets.append('paper-claimed evaluation')
    return list(dict.fromkeys(targets))


def infer_extracted_claims(intake: IntakeRecord) -> list[str]:
    claims: list[str] = []
    for item in intake.notes:
        cleaned = ' '.join(item.split())
        if cleaned:
            claims.append(cleaned[:240])
    if not claims:
        claims.append(intake.normalized_summary[:240])
    return claims[:3]


def infer_literature_state_summary(intake: IntakeRecord) -> str:
    notes_blob = ' '.join(intake.notes)
    if notes_blob:
        return f'Current bounded literature view: {notes_blob[:420]}'
    return f'Current bounded literature view is based on the intake summary: {intake.normalized_summary[:420]}'


def infer_research_gaps(
    intake: IntakeRecord,
    dataset_hints: list[str],
    evaluation_targets: list[str],
) -> list[str]:
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    gaps: list[str] = []
    if not dataset_hints:
        gaps.append('The literature snapshot does not settle on one concrete dataset for a bounded run.')
    if not evaluation_targets:
        gaps.append('The literature snapshot does not identify one canonical evaluation target or metric.')
    if 'baseline' not in lowered and 'benchmark' not in lowered:
        gaps.append('Baseline comparison expectations are still underspecified in the current literature context.')
    if intake.source_type == 'paper-link' and not intake.document_refs:
        gaps.append('A stored source document is missing, so interpretation still depends on URL-level context only.')
    return list(dict.fromkeys(gaps))[:4]


def infer_bounded_experiment_ideas(
    intake: IntakeRecord,
    candidate_workflows: list[str],
    dataset_hints: list[str],
) -> list[str]:
    ideas: list[str] = []
    if 'generic-tabular-benchmark' in candidate_workflows:
        dataset_label = dataset_hints[0] if dataset_hints else 'one approved tabular dataset'
        ideas.append(f'Run a bounded benchmark on {dataset_label} and compare the reported baseline against approved local baselines.')
    if 'literature-to-experiment' in candidate_workflows:
        ideas.append('Convert the reported method into a minimal literature-derived experiment with one dataset and one evaluation target.')
    if 'replication-lite' in candidate_workflows:
        ideas.append('Attempt a lightweight replication of the core reported claim with a reduced approved configuration.')
    return list(dict.fromkeys(ideas))[:3]


def build_document_context(intake: IntakeRecord, store: RunStore) -> str:
    parts: list[str] = []
    for document_id in intake.document_refs:
        record = store.get_source_document(document_id)
        if record is None:
            continue
        label = record.title or record.source_url
        if record.text_excerpt:
            parts.append(f'{label}: {record.text_excerpt}')
        else:
            parts.append(f'{label}: source document fetched without extracted text')
    return ' '.join(parts)


def build_interpretation_notes(intake: IntakeRecord, store: RunStore | None = None) -> list[str]:
    notes = list(intake.notes)
    if store is None:
        return notes
    document_context = build_document_context(intake, store)
    if document_context:
        return [document_context, *notes]
    return notes


def infer_unresolved_questions(intake: IntakeRecord, candidates: list[str], dataset_hints: list[str], evaluation_targets: list[str]) -> list[str]:
    unresolved: list[str] = []
    if not candidates:
        unresolved.append('Which approved workflow family should this request map to?')
    if not dataset_hints:
        unresolved.append('Which concrete dataset should the backend use?')
    if not evaluation_targets:
        unresolved.append('Which evaluation target or metric should be treated as canonical?')
    if intake.source_type == 'paper-link' and not intake.source_refs:
        unresolved.append('Which source reference should be treated as canonical for this paper intake?')
    return unresolved


def build_interpretation_record(intake: IntakeRecord, store: RunStore | None = None) -> InterpretationRecord:
    now = datetime.now(timezone.utc)
    candidate_workflows = list(dict.fromkeys([workflow for workflow in intake.workflow_family_candidates if workflow]))
    document_context = build_document_context(intake, store) if store is not None else ''
    enriched_intake = intake.model_copy(
        update={
            'notes': build_interpretation_notes(intake, store),
        }
    )
    dataset_hints = infer_dataset_hints(enriched_intake)
    evaluation_targets = infer_evaluation_targets(enriched_intake)
    extracted_claims = infer_extracted_claims(enriched_intake)
    literature_state_summary = infer_literature_state_summary(enriched_intake)
    research_gaps = infer_research_gaps(enriched_intake, dataset_hints, evaluation_targets)
    bounded_experiment_ideas = infer_bounded_experiment_ideas(enriched_intake, candidate_workflows, dataset_hints)
    unresolved_questions = infer_unresolved_questions(intake, candidate_workflows, dataset_hints, evaluation_targets)
    return InterpretationRecord(
        interpretation_id=uuid4().hex,
        intake_id=intake.intake_id,
        created_at=now,
        updated_at=now,
        status='ready_for_assessment' if not unresolved_questions else 'needs_review',
        source_type=intake.source_type,
        normalized_summary=intake.normalized_summary,
        extracted_method_summary=(
            f"Interpreted intake as {', '.join(candidate_workflows) or 'unmapped research work'} "
            f"with source type {intake.source_type}."
            + (' Used stored source-document context.' if document_context else '')
        ),
        literature_state_summary=literature_state_summary,
        candidate_workflow_families=candidate_workflows,
        dataset_hints=dataset_hints,
        evaluation_targets=evaluation_targets,
        extracted_claims=extracted_claims,
        research_gaps=research_gaps,
        bounded_experiment_ideas=bounded_experiment_ideas,
        unresolved_questions=unresolved_questions,
        submitted_by=intake.submitted_by,
        session_id=intake.session_id,
    )


def normalize_unique_strings(values: list[str]) -> list[str]:
    cleaned = [' '.join(item.split()) for item in values if item and item.strip()]
    return list(dict.fromkeys(cleaned))


def validate_interpretation_agent_draft(
    draft: dict[str, Any],
    intake: IntakeRecord,
    registry: WorkflowRegistry,
) -> dict[str, Any]:
    required_string_fields = ('source_type', 'normalized_summary', 'extracted_method_summary', 'literature_state_summary')
    for field_name in required_string_fields:
        value = draft.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'interpretation agent draft missing valid {field_name}')

    normalized = {
        'source_type': draft['source_type'].strip(),
        'normalized_summary': ' '.join(draft['normalized_summary'].split())[:500],
        'extracted_method_summary': ' '.join(draft['extracted_method_summary'].split())[:500],
        'literature_state_summary': ' '.join(draft['literature_state_summary'].split())[:500],
        'candidate_workflow_families': normalize_unique_strings(list(draft.get('candidate_workflow_families', []))),
        'dataset_hints': normalize_unique_strings(list(draft.get('dataset_hints', []))),
        'evaluation_targets': normalize_unique_strings(list(draft.get('evaluation_targets', []))),
        'extracted_claims': normalize_unique_strings(list(draft.get('extracted_claims', [])))[:3],
        'research_gaps': normalize_unique_strings(list(draft.get('research_gaps', [])))[:4],
        'bounded_experiment_ideas': normalize_unique_strings(list(draft.get('bounded_experiment_ideas', [])))[:3],
        'unresolved_questions': normalize_unique_strings(list(draft.get('unresolved_questions', []))),
    }

    invalid_workflows = [
        workflow_id for workflow_id in normalized['candidate_workflow_families']
        if registry.get_workflow(workflow_id) is None
    ]
    if invalid_workflows:
        raise ValueError(f'interpretation agent returned unapproved workflow ids: {", ".join(invalid_workflows)}')

    return normalized


def build_interpretation_record_from_agent_draft(
    intake: IntakeRecord,
    validated_draft: dict[str, Any],
) -> InterpretationRecord:
    now = datetime.now(timezone.utc)
    unresolved_questions = list(validated_draft['unresolved_questions'])
    return InterpretationRecord(
        interpretation_id=uuid4().hex,
        intake_id=intake.intake_id,
        created_at=now,
        updated_at=now,
        status='ready_for_assessment' if not unresolved_questions else 'needs_review',
        source_type=validated_draft['source_type'],
        normalized_summary=validated_draft['normalized_summary'],
        extracted_method_summary=validated_draft['extracted_method_summary'],
        literature_state_summary=validated_draft['literature_state_summary'],
        candidate_workflow_families=validated_draft['candidate_workflow_families'],
        dataset_hints=validated_draft['dataset_hints'],
        evaluation_targets=validated_draft['evaluation_targets'],
        extracted_claims=validated_draft['extracted_claims'],
        research_gaps=validated_draft['research_gaps'],
        bounded_experiment_ideas=validated_draft['bounded_experiment_ideas'],
        unresolved_questions=unresolved_questions,
        submitted_by=intake.submitted_by,
        session_id=intake.session_id,
    )


def call_interpretation_agent(
    intake: IntakeRecord,
    settings: Settings,
    registry: WorkflowRegistry,
    store: RunStore,
) -> InterpretationRecord | None:
    if not settings.interpretation_agent_enabled:
        return None

    payload = {
        'request_id': intake.intake_id,
        'intake': {
            'intake_id': intake.intake_id,
            'source_type': intake.source_type,
            'source_refs': intake.source_refs,
            'document_refs': intake.document_refs,
            'raw_request': intake.raw_request,
            'normalized_summary': intake.normalized_summary,
            'workflow_family_candidates': intake.workflow_family_candidates,
            'notes': build_interpretation_notes(intake, store),
            'submitted_by': intake.submitted_by,
        },
    }
    request_obj = urllib_request.Request(
        settings.interpretation_agent_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=settings.interpretation_agent_timeout_seconds) as response:
            body = json.loads(response.read().decode('utf-8'))
        draft = body.get('draft')
        if not isinstance(draft, dict):
            raise ValueError('interpretation agent response missing draft object')
        validated_draft = validate_interpretation_agent_draft(draft, intake, registry)
        return build_interpretation_record_from_agent_draft(intake, validated_draft)
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning('interpretation-agent fallback for intake %s: %s', intake.intake_id, exc)
        return None


def build_replicability_assessment(
    interpretation: InterpretationRecord,
    registry: WorkflowRegistry,
) -> ReplicabilityAssessmentRecord:
    now = datetime.now(timezone.utc)
    recommended_workflow = None
    approval_tier = None
    for workflow_id in interpretation.candidate_workflow_families:
        workflow = registry.get_workflow(workflow_id)
        if workflow is None:
            continue
        if recommended_workflow is None:
            recommended_workflow = workflow
        if workflow.workflow_id == 'generic-tabular-benchmark' and 'titanic' in interpretation.dataset_hints:
            recommended_workflow = workflow
            break

    unresolved_fields = list(dict.fromkeys(interpretation.unresolved_questions))
    blocking_reasons: list[str] = []
    recommendation = 'needs_review'
    status_value = 'needs_review'
    assessment_notes: list[str] = []

    if interpretation.research_gaps:
        assessment_notes.append(
            'Interpretation surfaced research gaps: ' + '; '.join(interpretation.research_gaps[:2])
        )
    if interpretation.bounded_experiment_ideas:
        assessment_notes.append(
            'Bounded experiment ideas: ' + '; '.join(interpretation.bounded_experiment_ideas[:2])
        )

    if recommended_workflow is not None:
        approval_tier = recommended_workflow.approval_tier
        assessment_notes.append(
            f"Best current approved workflow match is {recommended_workflow.workflow_id}."
        )
        assessment_notes.append(interpretation.literature_state_summary[:240])
        if recommended_workflow.approval_tier != 'tier-2-approved-execution':
            unresolved_fields.append(
                f'Approval tier {recommended_workflow.approval_tier} requires human review before execution.'
            )
            blocking_reasons.append('Approval tier requires explicit review.')
        if unresolved_fields:
            recommendation = 'needs_review'
            status_value = 'needs_review'
            assessment_notes.append('Interpretation still contains unresolved execution-critical fields.')
        else:
            recommendation = 'proceed'
            status_value = 'ready_for_design'
            assessment_notes.append('Interpretation can proceed toward design drafting.')
    else:
        recommendation = 'reject'
        status_value = 'rejected'
        blocking_reasons.append('No approved workflow family could be mapped from the interpretation.')
        assessment_notes.append('No approved workflow mapping was found in the current registry.')

    return ReplicabilityAssessmentRecord(
        assessment_id=uuid4().hex,
        interpretation_id=interpretation.interpretation_id,
        intake_id=interpretation.intake_id,
        created_at=now,
        updated_at=now,
        status=status_value,
        recommendation=recommendation,
        recommended_workflow_id=recommended_workflow.workflow_id if recommended_workflow is not None else None,
        candidate_workflow_families=interpretation.candidate_workflow_families,
        unresolved_fields=unresolved_fields,
        blocking_reasons=blocking_reasons,
        approval_tier=approval_tier,
        assessment_notes=assessment_notes,
        submitted_by=interpretation.submitted_by,
        session_id=interpretation.session_id,
    )


def validate_assessment_agent_draft(
    draft: dict[str, Any],
    interpretation: InterpretationRecord,
    registry: WorkflowRegistry,
) -> dict[str, Any]:
    status_value = draft.get('status')
    recommendation = draft.get('recommendation')
    if not isinstance(status_value, str) or not status_value.strip():
        raise ValueError('assessment agent draft missing valid status')
    if not isinstance(recommendation, str) or not recommendation.strip():
        raise ValueError('assessment agent draft missing valid recommendation')

    recommended_workflow_id = draft.get('recommended_workflow_id')
    if recommended_workflow_id is not None:
        if not isinstance(recommended_workflow_id, str) or not recommended_workflow_id.strip():
            raise ValueError('assessment agent draft has invalid recommended_workflow_id')
        if registry.get_workflow(recommended_workflow_id) is None:
            raise ValueError(f'assessment agent returned unapproved workflow id: {recommended_workflow_id}')
        recommended_workflow_id = recommended_workflow_id.strip()

    normalized = {
        'status': status_value.strip(),
        'recommendation': recommendation.strip(),
        'recommended_workflow_id': recommended_workflow_id,
        'candidate_workflow_families': normalize_unique_strings(list(draft.get('candidate_workflow_families', []))),
        'unresolved_fields': normalize_unique_strings(list(draft.get('unresolved_fields', [])))[:6],
        'blocking_reasons': normalize_unique_strings(list(draft.get('blocking_reasons', []))),
        'approval_tier': draft.get('approval_tier').strip() if isinstance(draft.get('approval_tier'), str) else None,
        'assessment_notes': normalize_unique_strings(list(draft.get('assessment_notes', []))),
    }

    invalid_candidates = [
        workflow_id for workflow_id in normalized['candidate_workflow_families']
        if registry.get_workflow(workflow_id) is None
    ]
    if invalid_candidates:
        raise ValueError(f'assessment agent returned unapproved candidate ids: {", ".join(invalid_candidates)}')

    return normalized


def build_replicability_assessment_from_agent_draft(
    interpretation: InterpretationRecord,
    validated_draft: dict[str, Any],
) -> ReplicabilityAssessmentRecord:
    now = datetime.now(timezone.utc)
    return ReplicabilityAssessmentRecord(
        assessment_id=uuid4().hex,
        interpretation_id=interpretation.interpretation_id,
        intake_id=interpretation.intake_id,
        created_at=now,
        updated_at=now,
        status=validated_draft['status'],
        recommendation=validated_draft['recommendation'],
        recommended_workflow_id=validated_draft['recommended_workflow_id'],
        candidate_workflow_families=validated_draft['candidate_workflow_families'],
        unresolved_fields=validated_draft['unresolved_fields'],
        blocking_reasons=validated_draft['blocking_reasons'],
        approval_tier=validated_draft['approval_tier'],
        assessment_notes=validated_draft['assessment_notes'],
        submitted_by=interpretation.submitted_by,
        session_id=interpretation.session_id,
    )


def call_assessment_agent(
    interpretation: InterpretationRecord,
    settings: Settings,
    registry: WorkflowRegistry,
) -> ReplicabilityAssessmentRecord | None:
    if not settings.assessment_agent_enabled:
        return None

    available_workflows = []
    for workflow_id in interpretation.candidate_workflow_families:
        workflow = registry.get_workflow(workflow_id)
        if workflow is None:
            continue
        available_workflows.append(
            {
                'workflow_id': workflow.workflow_id,
                'approval_tier': workflow.approval_tier,
            }
        )

    payload = {
        'request_id': interpretation.interpretation_id,
        'interpretation': {
            'interpretation_id': interpretation.interpretation_id,
            'intake_id': interpretation.intake_id,
            'source_type': interpretation.source_type,
            'normalized_summary': interpretation.normalized_summary,
            'extracted_method_summary': interpretation.extracted_method_summary,
            'literature_state_summary': interpretation.literature_state_summary,
            'candidate_workflow_families': interpretation.candidate_workflow_families,
            'dataset_hints': interpretation.dataset_hints,
            'evaluation_targets': interpretation.evaluation_targets,
            'extracted_claims': interpretation.extracted_claims,
            'research_gaps': interpretation.research_gaps,
            'bounded_experiment_ideas': interpretation.bounded_experiment_ideas,
            'unresolved_questions': interpretation.unresolved_questions,
            'submitted_by': interpretation.submitted_by,
        },
        'available_workflows': available_workflows,
    }
    request_obj = urllib_request.Request(
        settings.assessment_agent_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=settings.assessment_agent_timeout_seconds) as response:
            body = json.loads(response.read().decode('utf-8'))
        draft = body.get('draft')
        if not isinstance(draft, dict):
            raise ValueError('assessment agent response missing draft object')
        validated_draft = validate_assessment_agent_draft(draft, interpretation, registry)
        return build_replicability_assessment_from_agent_draft(interpretation, validated_draft)
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning('assessment-agent fallback for interpretation %s: %s', interpretation.interpretation_id, exc)
        return None


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
        if intake.document_refs:
            design_notes.append(f'Stored source documents are available: {", ".join(intake.document_refs[:2])}.')
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


def compute_unresolved_inputs(declared_inputs: dict[str, Any]) -> list[str]:
    return [
        name for name, value in declared_inputs.items() if isinstance(value, str) and value.startswith(UNRESOLVED_PREFIX)
    ]


def default_paper_pipeline_request_text(paper_ref: str) -> str:
    return (
        f'Ingest the approved paper {paper_ref} and derive a bounded, reproducible experiment '
        'using an approved workflow.'
    )


def build_fresh_paper_intake_request(
    request: FreshPaperPipelineRequest,
    settings: Settings,
) -> IntakeCreateRequest:
    notes = list(request.notes)
    if request.dataset_uri:
        notes.append(f'Preferred dataset uri: {request.dataset_uri}')
    return IntakeCreateRequest(
        raw_request=(request.raw_request or default_paper_pipeline_request_text(request.paper_ref)).strip(),
        source_refs=[request.paper_ref],
        source_type='paper-link',
        notes=notes,
        submitted_by=request.submitted_by or settings.default_submitted_by,
    )


def resolve_replication_repository_url(intake: IntakeRecord) -> str | None:
    for ref in intake.source_refs:
        lowered = ref.strip().lower()
        if lowered.startswith('https://github.com/') or lowered.startswith('http://github.com/'):
            return ref.strip()
    return None


def auto_resolve_pipeline_design_inputs(
    design: DesignDraftRecord,
    intake: IntakeRecord,
    interpretation: InterpretationRecord,
    request: FreshPaperPipelineRequest,
) -> tuple[dict[str, Any], list[str]]:
    resolved_inputs: dict[str, Any] = {}
    review_notes: list[str] = []
    lowered = ' '.join(
        [
            intake.raw_request,
            intake.normalized_summary,
            *intake.notes,
            *intake.source_refs,
            *interpretation.dataset_hints,
            *interpretation.evaluation_targets,
        ]
    ).lower()

    if design.workflow_id == 'literature-to-experiment':
        dataset_uri = request.dataset_uri
        if not dataset_uri:
            if 'titanic' in lowered:
                dataset_uri = 's3://datasets/titanic/train.csv'
                review_notes.append('Auto-resolved literature dataset_uri to approved Titanic dataset.')
            else:
                dataset_uri = 's3://datasets/paper-derived/train.csv'
                review_notes.append('Auto-resolved literature dataset_uri to bounded paper-derived dataset placeholder.')
        resolved_inputs['dataset_uri'] = dataset_uri
    elif design.workflow_id == 'replication-lite':
        repository_url = resolve_replication_repository_url(intake)
        if repository_url:
            resolved_inputs['repository_url'] = repository_url
            review_notes.append('Auto-resolved repository_url from GitHub source reference.')
        if request.dataset_uri:
            resolved_inputs['dataset_uri'] = request.dataset_uri
            review_notes.append('Applied caller-provided dataset_uri for replication pipeline.')
        else:
            resolved_inputs['dataset_uri'] = 's3://datasets/replication-lite/input.csv'
            review_notes.append('Auto-resolved replication dataset_uri to bounded default input.')
        if interpretation.evaluation_targets:
            resolved_inputs['evaluation_target'] = interpretation.evaluation_targets[0]
            review_notes.append('Auto-resolved evaluation_target from interpretation output.')
        else:
            resolved_inputs['evaluation_target'] = 'baseline comparison'
            review_notes.append('Auto-resolved evaluation_target to bounded baseline comparison default.')

    return resolved_inputs, review_notes


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
    paper_ref = chosen_paper.official_page or chosen_paper.pdf_url or chosen_paper.paper_id
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


def build_research_problem_request_from_session(
    session: ResearchSessionRecord,
    settings: Settings,
) -> ResearchProblemPipelineRequest:
    return ResearchProblemPipelineRequest(
        problem_statement=session.goal_statement,
        max_candidate_papers=5,
        priorities=session.priorities,
        submitted_by=session.submitted_by or settings.default_submitted_by,
        wait_for_terminal_state=False,
    )


def build_paper_intake_queue_record(
    request: PaperIntakeQueueCreateRequest,
    selected_track_ids: list[str],
    selected_queries: list[str],
    selected_papers: list[ResearchProblemPaperCandidate],
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
        warnings=warnings,
        candidates=candidates,
        submitted_by=request.submitted_by or settings.default_submitted_by,
        session_id=session_id,
    )


def build_intake_request_from_problem_candidate(
    queue: PaperIntakeQueueRecord,
    candidate: PaperIntakeCandidateRecord,
    document_refs: list[str] | None = None,
) -> IntakeCreateRequest:
    paper_ref = candidate.official_page or candidate.pdf_url or candidate.paper_id
    notes = [candidate.why_seed]
    notes.extend(candidate.first_jobs[:2])
    if queue.selected_tracks:
        notes.append('Selected tracks: ' + ', '.join(queue.selected_tracks))
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


def guess_document_title(source_url: str) -> str:
    parsed = source_url.rstrip('/').rsplit('/', 1)[-1]
    return parsed or 'source-document'


def extract_text_excerpt(content: bytes, content_type: str | None, source_url: str) -> str | None:
    media_type = (content_type or '').split(';', 1)[0].strip().lower()
    try:
        if media_type in {'text/html', 'application/xhtml+xml'} or source_url.lower().endswith(('.html', '.htm')):
            decoded = content.decode('utf-8', errors='ignore')
            stripped = HTML_TAG_RE.sub(' ', decoded)
            normalized = ' '.join(html.unescape(stripped).split())
            return normalized[:4000] or None
        if media_type == 'text/plain':
            normalized = ' '.join(content.decode('utf-8', errors='ignore').split())
            return normalized[:4000] or None
        if media_type == 'application/pdf' or source_url.lower().endswith('.pdf'):
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            parts: list[str] = []
            for page in reader.pages[:5]:
                text = page.extract_text() or ''
                text = ' '.join(text.split())
                if text:
                    parts.append(text)
            joined = ' '.join(parts)
            return joined[:4000] or None
    except Exception:
        return None
    return None


def fetch_source_document_bytes(source_url: str) -> tuple[bytes, str | None]:
    request_obj = urllib_request.Request(
        source_url,
        headers={
            'User-Agent': 'glasslab-workflow-api/0.1.0',
            'Accept': 'text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.8',
        },
        method='GET',
    )
    with urllib_request.urlopen(request_obj, timeout=30.0) as response:
        content = response.read()
        content_type = response.headers.get('Content-Type')
    return content, content_type


def persist_source_document_bytes(
    *,
    document_id: str,
    source_url: str,
    content: bytes,
    content_type: str | None,
    settings: Settings,
) -> str:
    guessed_ext = mimetypes.guess_extension((content_type or '').split(';', 1)[0].strip()) or ''
    if not guessed_ext:
        if source_url.lower().endswith('.pdf'):
            guessed_ext = '.pdf'
        elif source_url.lower().endswith(('.html', '.htm')):
            guessed_ext = '.html'
    key_name = f'{document_id}/source{guessed_ext}'

    if settings.source_document_storage_mode == 'minio':
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError('minio package is required for source_document_storage_mode=minio') from exc

        if not settings.minio_access_key or not settings.minio_secret_key:
            raise RuntimeError('minio credentials are required for source_document_storage_mode=minio')

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        bucket = settings.source_document_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket,
            key_name,
            BytesIO(content),
            length=len(content),
            content_type=(content_type or 'application/octet-stream'),
        )
        return f's3://{bucket}/{key_name}'

    base_dir = Path(settings.source_document_storage_dir)
    target = base_dir / document_id / f'source{guessed_ext}'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target.as_uri()


def ingest_source_document(
    source_url: str,
    submitted_by: str,
    settings: Settings,
    store: RunStore,
    session_id: str | None = None,
) -> SourceDocumentRecord:
    now = datetime.now(timezone.utc)
    document_id = uuid4().hex
    try:
        content, content_type = fetch_source_document_bytes(source_url)
        storage_uri = persist_source_document_bytes(
            document_id=document_id,
            source_url=source_url,
            content=content,
            content_type=content_type,
            settings=settings,
        )
        record = SourceDocumentRecord(
            document_id=document_id,
            created_at=now,
            updated_at=now,
            status='fetched',
            source_url=source_url,
            submitted_by=submitted_by,
            storage_uri=storage_uri,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            title=guess_document_title(source_url),
            text_excerpt=extract_text_excerpt(content, content_type, source_url),
            session_id=session_id,
        )
    except Exception as exc:
        record = SourceDocumentRecord(
            document_id=document_id,
            created_at=now,
            updated_at=now,
            status='fetch-failed',
            source_url=source_url,
            submitted_by=submitted_by,
            fetch_error=str(exc),
            title=guess_document_title(source_url),
            session_id=session_id,
        )
    store.save_source_document(record)
    return record


def build_design_draft(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    source_assessment_id: str | None = None,
) -> DesignDraftRecord:
    now = datetime.now(timezone.utc)
    design_id = uuid4().hex
    declared_inputs, unresolved_inputs, design_notes = derive_design_from_intake(intake, workflow)
    bounded_idea_notes = [note for note in intake.notes if note.startswith('Bounded experiment ideas: ')]
    literature_state_notes = [note for note in intake.notes if note.startswith('Literature state: ')]
    design_notes.extend(bounded_idea_notes[:1])
    design_notes.extend(literature_state_notes[:1])
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
        source_assessment_id=source_assessment_id,
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
        session_id=intake.session_id,
    )


def validate_design_agent_draft(
    draft: dict[str, Any],
    workflow: WorkflowRegistryEntry,
) -> dict[str, Any]:
    required_string_fields = ('workflow_id', 'workflow_family', 'objective', 'resource_profile', 'approval_tier')
    for field_name in required_string_fields:
        value = draft.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'design agent draft missing valid {field_name}')

    if draft['workflow_id'].strip() != workflow.workflow_id:
        raise ValueError('design agent draft changed workflow_id')
    if draft['workflow_family'].strip() != workflow.workflow_family:
        raise ValueError('design agent draft changed workflow_family')
    if draft['resource_profile'].strip() != workflow.resource_profile.profile_name:
        raise ValueError('design agent draft changed resource_profile')
    if draft['approval_tier'].strip() != workflow.approval_tier:
        raise ValueError('design agent draft changed approval_tier')

    candidate_models = normalize_unique_strings(list(draft.get('candidate_models', [])))
    invalid_models = [model for model in candidate_models if model not in workflow.allowed_models]
    if invalid_models:
        raise ValueError(f'design agent returned disallowed models: {", ".join(invalid_models)}')

    declared_inputs = draft.get('declared_inputs', {})
    expected_artifacts = draft.get('expected_artifacts', {})
    if not isinstance(declared_inputs, dict):
        raise ValueError('design agent draft missing valid declared_inputs')
    if not isinstance(expected_artifacts, dict):
        raise ValueError('design agent draft missing valid expected_artifacts')

    normalized = {
        'workflow_id': draft['workflow_id'].strip(),
        'workflow_family': draft['workflow_family'].strip(),
        'objective': ' '.join(draft['objective'].split())[:500],
        'declared_inputs': declared_inputs,
        'unresolved_inputs': normalize_unique_strings(list(draft.get('unresolved_inputs', []))),
        'candidate_models': candidate_models,
        'resource_profile': draft['resource_profile'].strip(),
        'expected_artifacts': expected_artifacts,
        'approval_tier': draft['approval_tier'].strip(),
        'design_notes': normalize_unique_strings(list(draft.get('design_notes', []))),
    }
    return normalized


def build_design_draft_from_agent_draft(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    validated_draft: dict[str, Any],
    source_assessment_id: str | None = None,
) -> DesignDraftRecord:
    now = datetime.now(timezone.utc)
    return DesignDraftRecord(
        design_id=uuid4().hex,
        intake_id=intake.intake_id,
        source_assessment_id=source_assessment_id,
        created_at=now,
        updated_at=now,
        status='ready_for_run' if not validated_draft['unresolved_inputs'] and workflow.approval_tier == 'tier-2-approved-execution' else 'needs_review',
        workflow_id=validated_draft['workflow_id'],
        workflow_family=validated_draft['workflow_family'],
        objective=validated_draft['objective'],
        declared_inputs=validated_draft['declared_inputs'],
        unresolved_inputs=validated_draft['unresolved_inputs'],
        candidate_models=validated_draft['candidate_models'],
        resource_profile=validated_draft['resource_profile'],
        expected_artifacts=validated_draft['expected_artifacts'],
        approval_tier=validated_draft['approval_tier'],
        design_notes=validated_draft['design_notes'],
        submitted_by=submitted_by,
        session_id=intake.session_id,
    )


def call_design_agent(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    settings: Settings,
    source_assessment_id: str | None = None,
) -> DesignDraftRecord | None:
    if not settings.design_agent_enabled:
        return None

    payload = {
        'request_id': intake.intake_id,
        'intake': {
            'intake_id': intake.intake_id,
            'source_type': intake.source_type,
            'source_refs': intake.source_refs,
            'document_refs': intake.document_refs,
            'raw_request': intake.raw_request,
            'normalized_summary': intake.normalized_summary,
            'workflow_family_candidates': intake.workflow_family_candidates,
            'notes': intake.notes,
            'submitted_by': intake.submitted_by,
        },
        'workflow': {
            'workflow_id': workflow.workflow_id,
            'workflow_family': workflow.workflow_family,
            'allowed_models': workflow.allowed_models,
            'expected_artifacts': workflow.expected_artifacts.model_dump(mode='json'),
            'resource_profile_name': workflow.resource_profile.profile_name,
            'approval_tier': workflow.approval_tier,
        },
    }
    request_obj = urllib_request.Request(
        settings.design_agent_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=settings.design_agent_timeout_seconds) as response:
            body = json.loads(response.read().decode('utf-8'))
        draft = body.get('draft')
        if not isinstance(draft, dict):
            raise ValueError('design agent response missing draft object')
        validated_draft = validate_design_agent_draft(draft, workflow)
        return build_design_draft_from_agent_draft(
            intake,
            workflow,
            submitted_by=submitted_by,
            validated_draft=validated_draft,
            source_assessment_id=source_assessment_id,
        )
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning('design-agent fallback for intake %s workflow %s: %s', intake.intake_id, workflow.workflow_id, exc)
        return None


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
        touch_research_session(store, record.session_id, latest_interpretation_id=record.interpretation_id)
        return record

    @app.post('/research-sessions/{session_id}/skills/interpretation', response_model=InterpretationRecord, status_code=status.HTTP_201_CREATED)
    def apply_session_interpretation_skill(session_id: str) -> InterpretationRecord:
        intake = get_required_session_latest_intake(store, session_id)
        return create_interpretation_for_intake(intake)

    @app.post('/research-sessions/latest/skills/interpretation', response_model=InterpretationRecord, status_code=status.HTTP_201_CREATED)
    def apply_latest_session_interpretation_skill() -> InterpretationRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return apply_session_interpretation_skill(session.session_id)

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
        touch_research_session(store, record.session_id, latest_assessment_id=record.assessment_id)
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
        build_research_problem_request_from_session=lambda *args, **kwargs: build_research_problem_request_from_session(*args, **kwargs),
        build_research_problem_record=lambda *args, **kwargs: build_research_problem_record(*args, **kwargs),
        build_research_problem_request_from_record=lambda *args, **kwargs: build_research_problem_request_from_record(*args, **kwargs),
        touch_research_session=lambda *args, **kwargs: touch_research_session(*args, **kwargs),
        build_paper_intake_queue_record=lambda *args, **kwargs: build_paper_intake_queue_record(*args, **kwargs),
        ingest_source_document=lambda *args, **kwargs: ingest_source_document(*args, **kwargs),
        build_intake_request_from_problem_candidate=lambda *args, **kwargs: build_intake_request_from_problem_candidate(*args, **kwargs),
        stage_intake_from_request=lambda *args, **kwargs: stage_intake_from_request(*args, **kwargs),
        record_operation=lambda *args, **kwargs: record_operation(*args, **kwargs),
    )

    @app.get('/source-documents', response_model=list[SourceDocumentRecord])
    def list_source_documents() -> list[SourceDocumentRecord]:
        return store.list_source_documents()

    @app.get('/source-documents/latest', response_model=SourceDocumentRecord)
    def get_latest_source_document() -> SourceDocumentRecord:
        record = store.get_latest_source_document()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='source document not found')
        return record

    @app.get('/source-documents/{document_id}', response_model=SourceDocumentRecord)
    def get_source_document(document_id: str) -> SourceDocumentRecord:
        record = store.get_source_document(document_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='source document not found')
        return record

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
                execution_status=entry.execution_status,
                submission_backend=entry.submission_backend,
                execution_blockers=entry.execution_blockers,
            )
            for entry in registry.list_workflows()
        ]

    @app.get('/workflow-families/{workflow_id}/execution-preflight', response_model=ExecutionPreflightResult)
    def get_workflow_execution_preflight(workflow_id: str) -> ExecutionPreflightResult:
        workflow = registry.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='workflow not found')
        return build_execution_preflight_result(workflow, settings)

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
            session_id=design.session_id,
        )

    @app.get('/runs/{run_id}', response_model=RunRecord)
    def get_run(run_id: str) -> RunRecord:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        return record.model_copy(update={'status': resolve_run_status(record, settings, submitter)})

    @app.get('/runs/{run_id}/artifacts', response_model=RunArtifactsResponse)
    def get_run_artifacts(run_id: str) -> RunArtifactsResponse:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        artifacts = load_artifacts_from_disk(settings, run_id) or store.get_artifacts(run_id)
        if artifacts is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='artifacts not found')
        return RunArtifactsResponse(run_id=run_id, artifacts=artifacts)

    @app.get('/runs/{run_id}/logs', response_model=RunLogsResponse)
    def get_run_logs(run_id: str) -> RunLogsResponse:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        logs = load_logs_from_disk(settings, run_id)
        if not logs:
            logs = submitter.get_live_logs(record) or store.get_logs(run_id)
        return RunLogsResponse(run_id=run_id, logs=logs)

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
