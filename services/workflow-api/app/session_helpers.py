from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Callable

from fastapi import HTTPException, status

from .config import Settings
from .persistence import RunStore
from .schemas import (
    IntakeRecord,
    InterpretationRecord,
    LiteratureDigestResponse,
    ResearchProblemPipelineRequest,
    ResearchSessionContextResponse,
    ResearchSessionCreateRequest,
    ResearchSessionRecord,
    ReplicabilityAssessmentRecord,
    DesignDraftRecord,
    ResearchProblemRecord,
)


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


def create_research_session_from_problem(
    problem: ResearchProblemRecord,
    settings: Settings,
    build_research_session_record: Callable[[ResearchSessionCreateRequest, Settings], ResearchSessionRecord],
) -> ResearchSessionRecord:
    request = ResearchSessionCreateRequest(
        title=None,
        goal_statement=problem.problem_statement,
        priorities=problem.priorities,
        submitted_by=problem.submitted_by,
    )
    return build_research_session_record(request, settings)


def build_research_problem_request_from_session(
    session: ResearchSessionRecord,
    settings: Settings,
) -> ResearchProblemPipelineRequest:
    return ResearchProblemPipelineRequest(
        problem_statement=session.goal_statement,
        max_candidate_papers=2,
        priorities=session.priorities,
        submitted_by=session.submitted_by or settings.default_submitted_by,
        wait_for_terminal_state=False,
    )


def touch_research_session(
    store: RunStore,
    session_id: str | None,
    **updates: Any,
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


def append_research_session_memory(
    store: RunStore,
    session_id: str,
    *,
    working_note: str | None = None,
    decision: str | None = None,
    experiment_idea: str | None = None,
) -> ResearchSessionRecord:
    session = get_required_research_session(store, session_id)

    def append_unique(items: list[str], value: str | None) -> list[str]:
        updated = list(items)
        if value and value not in updated:
            updated.append(value)
        return updated

    updated = session.model_copy(
        update={
            'working_notes': append_unique(session.working_notes, working_note),
            'decision_log': append_unique(session.decision_log, decision),
            'next_experiment_ideas': append_unique(session.next_experiment_ideas, experiment_idea),
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


def build_research_session_literature_digest(
    session: ResearchSessionRecord,
    store: RunStore,
) -> LiteratureDigestResponse:
    source_documents = [
        record
        for record in store.list_source_documents()
        if record.session_id == session.session_id
    ]
    source_documents.sort(key=lambda record: record.created_at, reverse=True)

    matched_document_count = sum(1 for record in source_documents if record.validation_status == 'matched')
    mismatched_document_count = sum(1 for record in source_documents if record.validation_status == 'mismatch')
    fetch_failed_document_count = sum(1 for record in source_documents if record.status == 'fetch-failed')

    def top_terms(values: list[str]) -> list[str]:
        counts: dict[str, int] = {}
        first_seen: dict[str, datetime] = {}
        for record in source_documents:
            for value in values_for_record(record, values):
                counts[value] = counts.get(value, 0) + 1
                first_seen.setdefault(value, record.created_at)
        ranked = sorted(
            counts,
            key=lambda value: (-counts[value], -first_seen[value].timestamp(), value),
        )
        return ranked[:8]

    def values_for_record(record: Any, attribute_names: list[str]) -> list[str]:
        items: list[str] = []
        for attribute_name in attribute_names:
            items.extend(getattr(record, attribute_name))
        return list(dict.fromkeys(item for item in items if item))

    top_methods = top_terms(['method_hints'])
    top_datasets = top_terms(['dataset_hints'])
    top_losses = top_terms(['loss_hints'])
    top_architectures = top_terms(['architecture_hints'])
    top_baselines = top_terms(['baseline_hints'])
    top_metrics = top_terms(['metric_hints'])
    top_domain_tasks = top_terms(['domain_task_hints'])
    notable_titles = list(
        dict.fromkeys(
            record.title
            for record in source_documents
            if record.validation_status == 'matched' and record.title
        )
    )[:8]

    summary_notes: list[str] = []
    if matched_document_count:
        summary_notes.append(f'{matched_document_count} validated source document(s) are attached to this session.')
    if mismatched_document_count:
        summary_notes.append(f'{mismatched_document_count} fetched source document(s) did not match the expected paper title.')
    if fetch_failed_document_count:
        summary_notes.append(f'{fetch_failed_document_count} source fetch attempt(s) failed.')
    if top_methods:
        summary_notes.append(f'Method hints seen so far: {", ".join(top_methods[:4])}.')
    if top_datasets:
        summary_notes.append(f'Dataset hints seen so far: {", ".join(top_datasets[:4])}.')
    if top_losses:
        summary_notes.append(f'Losses seen so far: {", ".join(top_losses[:4])}.')
    if top_architectures:
        summary_notes.append(f'Architectures seen so far: {", ".join(top_architectures[:4])}.')
    if top_metrics:
        summary_notes.append(f'Metrics seen so far: {", ".join(top_metrics[:4])}.')
    if top_domain_tasks:
        summary_notes.append(f'Domain/task hints seen so far: {", ".join(top_domain_tasks[:4])}.')

    return LiteratureDigestResponse(
        session_id=session.session_id,
        source_documents=source_documents,
        matched_document_count=matched_document_count,
        mismatched_document_count=mismatched_document_count,
        fetch_failed_document_count=fetch_failed_document_count,
        top_methods=top_methods,
        top_datasets=top_datasets,
        top_losses=top_losses,
        top_architectures=top_architectures,
        top_baselines=top_baselines,
        top_metrics=top_metrics,
        top_domain_tasks=top_domain_tasks,
        notable_titles=notable_titles,
        summary_notes=summary_notes,
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
