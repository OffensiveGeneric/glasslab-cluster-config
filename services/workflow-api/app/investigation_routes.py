from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from .config import Settings
from .persistence import RunStore
from .schemas import (
    DesignDraftRecord,
    InvestigationClaimCreateRequest,
    InvestigationClaimRecord,
    InvestigationContextResponse,
    InvestigationCreateRequest,
    InvestigationEvidenceReference,
    InvestigationHypothesisCreateRequest,
    InvestigationHypothesisRecord,
    InvestigationPlanApprovalRecord,
    InvestigationPlanApproveRequest,
    InvestigationPlanSnapshot,
    InvestigationRecord,
    InvestigationRunResponse,
    ResearchSessionCreateRequest,
    ResearchSessionRecord,
    RunRecord,
)


TERMINAL_RUN_STATES = {'succeeded', 'failed', 'rejected'}


def build_plan_sha256(
    investigation: InvestigationRecord,
    design: DesignDraftRecord,
) -> str:
    snapshot = build_plan_snapshot(investigation, design)
    canonical = json.dumps(
        snapshot.model_dump(mode='json'),
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return sha256(canonical).hexdigest()


def build_plan_snapshot(
    investigation: InvestigationRecord,
    design: DesignDraftRecord,
) -> InvestigationPlanSnapshot:
    return InvestigationPlanSnapshot(
        investigation_id=investigation.investigation_id,
        research_mode=investigation.research_mode,
        research_question=investigation.research_question,
        hypotheses=list(investigation.hypotheses),
        design=design,
    )


def register_investigation_routes(
    app: FastAPI,
    *,
    settings: Settings,
    store: RunStore,
    build_research_session_record: Callable[
        [ResearchSessionCreateRequest, Settings],
        ResearchSessionRecord,
    ],
    launch_design_run: Callable[[DesignDraftRecord], RunRecord],
) -> None:
    def get_required_investigation(investigation_id: str) -> InvestigationRecord:
        record = store.get_investigation(investigation_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='investigation not found',
            )
        return record

    def get_active_approval(
        investigation: InvestigationRecord,
    ) -> InvestigationPlanApprovalRecord | None:
        if investigation.active_plan_approval_id is None:
            return None
        return next(
            (
                approval
                for approval in investigation.plan_approvals
                if approval.approval_id == investigation.active_plan_approval_id
            ),
            None,
        )

    def resolve_design(
        investigation: InvestigationRecord,
        design_id: str | None,
    ) -> DesignDraftRecord:
        session = store.get_research_session(investigation.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='investigation research session is missing',
            )
        resolved_design_id = design_id or session.latest_design_id
        if not resolved_design_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='investigation has no current design to approve',
            )
        design = store.get_design_draft(resolved_design_id)
        if design is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='design draft not found',
            )
        if design.session_id != investigation.session_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='design draft does not belong to this investigation',
            )
        return design

    @app.post(
        '/investigations',
        response_model=InvestigationRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_investigation(request: InvestigationCreateRequest) -> InvestigationRecord:
        submitted_by = request.submitted_by or settings.default_submitted_by
        session = build_research_session_record(
            ResearchSessionCreateRequest(
                title=request.title,
                goal_statement=request.research_question,
                priorities=request.priorities,
                submitted_by=submitted_by,
            ),
            settings,
        )
        now = datetime.now(timezone.utc)
        record = InvestigationRecord(
            investigation_id=uuid4().hex,
            session_id=session.session_id,
            created_at=now,
            updated_at=now,
            status='planning',
            title=session.title,
            research_question=request.research_question.strip(),
            research_mode=request.research_mode,
            hypotheses=[
                InvestigationHypothesisRecord(
                    hypothesis_id=uuid4().hex,
                    statement=statement,
                    created_at=now,
                    submitted_by=submitted_by,
                )
                for statement in request.hypotheses
            ],
            submitted_by=submitted_by,
        )
        store.save_research_session(session)
        store.save_investigation(record)
        return record

    @app.get('/investigations', response_model=list[InvestigationRecord])
    def list_investigations() -> list[InvestigationRecord]:
        return store.list_investigations()

    @app.get('/investigations/latest', response_model=InvestigationRecord)
    def get_latest_investigation() -> InvestigationRecord:
        record = store.get_latest_investigation()
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='no investigation has been created yet',
            )
        return record

    @app.get('/investigations/{investigation_id}', response_model=InvestigationRecord)
    def get_investigation(investigation_id: str) -> InvestigationRecord:
        return get_required_investigation(investigation_id)

    @app.get(
        '/investigations/{investigation_id}/context',
        response_model=InvestigationContextResponse,
    )
    def get_investigation_context(
        investigation_id: str,
    ) -> InvestigationContextResponse:
        investigation = get_required_investigation(investigation_id)
        session = store.get_research_session(investigation.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='investigation research session is missing',
            )
        approval = get_active_approval(investigation)
        current_design = (
            store.get_design_draft(session.latest_design_id)
            if session.latest_design_id
            else None
        )
        approved_design = (
            approval.plan_snapshot.design
            if approval is not None
            else None
        )
        runs = [
            run
            for run_id in investigation.run_ids
            if (run := store.get_run(run_id)) is not None
        ]
        return InvestigationContextResponse(
            investigation=investigation,
            session=session,
            current_design=current_design,
            approved_design=approved_design,
            runs=runs,
        )

    @app.post(
        '/investigations/{investigation_id}/hypotheses',
        response_model=InvestigationRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def add_investigation_hypothesis(
        investigation_id: str,
        request: InvestigationHypothesisCreateRequest,
    ) -> InvestigationRecord:
        investigation = get_required_investigation(investigation_id)
        if (
            investigation.research_mode == 'confirmatory'
            and investigation.active_plan_approval_id is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='confirmatory hypotheses are frozen after plan approval',
            )
        if any(
            hypothesis.statement == request.statement
            for hypothesis in investigation.hypotheses
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='hypothesis already exists in this investigation',
            )

        now = datetime.now(timezone.utc)
        hypotheses = [
            *investigation.hypotheses,
            InvestigationHypothesisRecord(
                hypothesis_id=uuid4().hex,
                statement=request.statement,
                created_at=now,
                submitted_by=request.submitted_by or settings.default_submitted_by,
            ),
        ]
        updated = investigation.model_copy(
            update={
                'updated_at': now,
                'status': 'planning',
                'hypotheses': hypotheses,
                'active_plan_approval_id': None,
            }
        )
        store.save_investigation(updated)
        return updated

    @app.post(
        '/investigations/{investigation_id}/plan-approvals',
        response_model=InvestigationRecord,
    )
    def approve_investigation_plan(
        investigation_id: str,
        request: InvestigationPlanApproveRequest,
    ) -> InvestigationRecord:
        investigation = get_required_investigation(investigation_id)
        if not investigation.hypotheses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='investigation needs at least one hypothesis before plan approval',
            )
        if investigation.research_mode == 'confirmatory' and investigation.run_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='a confirmatory plan cannot be replaced after execution begins',
            )
        design = resolve_design(investigation, request.design_id)
        method_spec = design.method_spec
        if method_spec is not None and method_spec.run_readiness != 'ready':
            detail = 'design method_spec is not ready for approval'
            if method_spec.blocking_reasons:
                detail += ': ' + '; '.join(method_spec.blocking_reasons[:2])
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            )
        if design.status != 'ready_for_run':
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='design draft is not ready for approval',
            )

        plan_snapshot = build_plan_snapshot(investigation, design)
        plan_sha256 = build_plan_sha256(investigation, design)
        active_approval = get_active_approval(investigation)
        if (
            active_approval is not None
            and active_approval.design_id == design.design_id
            and active_approval.plan_sha256 == plan_sha256
        ):
            return investigation

        now = datetime.now(timezone.utc)
        approval = InvestigationPlanApprovalRecord(
            approval_id=uuid4().hex,
            design_id=design.design_id,
            plan_sha256=plan_sha256,
            approved_at=now,
            approved_by=request.approved_by or settings.default_submitted_by,
            hypothesis_ids=[
                hypothesis.hypothesis_id
                for hypothesis in investigation.hypotheses
            ],
            research_mode=investigation.research_mode,
            plan_snapshot=plan_snapshot,
            evaluator_contract=(
                method_spec.evaluator_contract
                if method_spec is not None
                else None
            ),
            budget_contract=(
                method_spec.budget_contract
                if method_spec is not None
                else None
            ),
            note=request.note,
        )
        updated = investigation.model_copy(
            update={
                'updated_at': now,
                'status': 'approved',
                'plan_approvals': [*investigation.plan_approvals, approval],
                'active_plan_approval_id': approval.approval_id,
            }
        )
        store.save_investigation(updated)
        return updated

    @app.post(
        '/investigations/{investigation_id}/runs',
        response_model=InvestigationRunResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def launch_investigation_run(
        investigation_id: str,
    ) -> InvestigationRunResponse:
        investigation = get_required_investigation(investigation_id)
        approval = get_active_approval(investigation)
        if approval is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='investigation has no active plan approval',
            )
        design = resolve_design(investigation, approval.design_id)
        current_sha256 = build_plan_sha256(investigation, design)
        if current_sha256 != approval.plan_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='approved plan snapshot no longer matches the current investigation state',
            )

        run = launch_design_run(design)
        now = datetime.now(timezone.utc)
        updated = investigation.model_copy(
            update={
                'updated_at': now,
                'status': 'running',
                'run_ids': [*investigation.run_ids, run.run_id],
            }
        )
        store.save_investigation(updated)
        return InvestigationRunResponse(
            investigation=updated,
            approval=approval,
            design=design,
            run=run,
        )

    @app.post(
        '/investigations/{investigation_id}/claims',
        response_model=InvestigationClaimRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def record_investigation_claim(
        investigation_id: str,
        request: InvestigationClaimCreateRequest,
    ) -> InvestigationClaimRecord:
        investigation = get_required_investigation(investigation_id)
        known_hypothesis_ids = {
            hypothesis.hypothesis_id
            for hypothesis in investigation.hypotheses
        }
        unknown_hypothesis_ids = [
            hypothesis_id
            for hypothesis_id in request.hypothesis_ids
            if hypothesis_id not in known_hypothesis_ids
        ]
        if unknown_hypothesis_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    'message': 'claim references hypotheses outside this investigation',
                    'hypothesis_ids': unknown_hypothesis_ids,
                },
            )

        evidence_keys = [
            (item.run_id, item.artifact_name)
            for item in request.evidence
        ]
        if len(set(evidence_keys)) != len(evidence_keys):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='claim evidence entries must be unique',
            )

        evidence: list[InvestigationEvidenceReference] = []
        for item in request.evidence:
            if item.run_id not in investigation.run_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'run is not part of this investigation: {item.run_id}',
                )
            run = store.get_run(item.run_id)
            if run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f'run not found: {item.run_id}',
                )
            if run.status.status not in TERMINAL_RUN_STATES:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'run is not terminal: {item.run_id}',
                )
            if (
                request.assessment in {'supported', 'refuted'}
                and run.status.status != 'succeeded'
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='supported or refuted claims require successful runs',
                )
            artifact_ref = run.artifact_refs.get(item.artifact_name)
            if artifact_ref is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f'run {item.run_id} has no ingested artifact named '
                        f'{item.artifact_name}'
                    ),
                )
            evidence.append(
                InvestigationEvidenceReference(
                    run_id=item.run_id,
                    artifact_name=item.artifact_name,
                    artifact_ref=artifact_ref,
                )
            )

        now = datetime.now(timezone.utc)
        claim = InvestigationClaimRecord(
            claim_id=uuid4().hex,
            statement=request.statement,
            assessment=request.assessment,
            hypothesis_ids=request.hypothesis_ids,
            evidence=evidence,
            created_at=now,
            submitted_by=request.submitted_by or settings.default_submitted_by,
            note=request.note,
        )
        updated = investigation.model_copy(
            update={
                'updated_at': now,
                'status': 'evaluating',
                'claims': [*investigation.claims, claim],
            }
        )
        store.save_investigation(updated)
        return claim
