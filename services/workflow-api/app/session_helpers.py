from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from .config import Settings
from .persistence import RunStore
from .schemas import (
    IntakeRecord,
    InterpretationRecord,
    ResearchProblemPipelineRequest,
    ResearchSessionContextResponse,
    ResearchSessionCreateRequest,
    ResearchSessionRecord,
    ReplicabilityAssessmentRecord,
    DesignDraftRecord,
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
