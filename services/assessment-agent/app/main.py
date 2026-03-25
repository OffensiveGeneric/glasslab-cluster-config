from __future__ import annotations

from fastapi import FastAPI

from .models import (
    AssessmentDraft,
    AssessmentRequest,
    AssessmentResponse,
    HealthResponse,
    ModelBackendMetadata,
)

MODEL_BACKEND = ModelBackendMetadata(
    provider='ollama',
    base_url='http://192.168.1.23:11434',
    model='qwen3:30b',
    timeout_seconds=45.0,
)


def build_assessment_draft(request: AssessmentRequest) -> AssessmentDraft:
    interpretation = request.interpretation
    workflows = {workflow.workflow_id: workflow for workflow in request.available_workflows}

    recommended_workflow = None
    for workflow_id in interpretation.candidate_workflow_families:
        workflow = workflows.get(workflow_id)
        if workflow is None:
            continue
        if recommended_workflow is None:
            recommended_workflow = workflow
        if workflow.workflow_id == 'generic-tabular-benchmark' and 'titanic' in interpretation.dataset_hints:
            recommended_workflow = workflow
            break

    unresolved_fields = list(interpretation.unresolved_questions)
    blocking_reasons: list[str] = []
    assessment_notes: list[str] = []
    approval_tier = recommended_workflow.approval_tier if recommended_workflow is not None else None

    if interpretation.research_gaps:
        assessment_notes.append(
            'Interpretation surfaced research gaps: ' + '; '.join(interpretation.research_gaps[:2])
        )
    if interpretation.bounded_experiment_ideas:
        assessment_notes.append(
            'Bounded experiment ideas: ' + '; '.join(interpretation.bounded_experiment_ideas[:2])
        )

    if recommended_workflow is None:
        return AssessmentDraft(
            recommendation='reject',
            recommended_workflow_id=None,
            candidate_workflow_families=interpretation.candidate_workflow_families,
            unresolved_fields=unresolved_fields,
            blocking_reasons=['No approved workflow family could be mapped from the interpretation.'],
            approval_tier=None,
            assessment_notes=['No approved workflow mapping was found in the current registry view.'],
            status='rejected',
        )

    assessment_notes.append(f'Best current approved workflow match is {recommended_workflow.workflow_id}.')
    assessment_notes.append(interpretation.literature_state_summary[:240])
    if recommended_workflow.approval_tier != 'tier-2-approved-execution':
        unresolved_fields.append(
            f'Approval tier {recommended_workflow.approval_tier} requires human review before execution.'
        )
        blocking_reasons.append('Approval tier requires explicit review.')

    if unresolved_fields:
        assessment_notes.append('Interpretation still contains unresolved execution-critical fields.')
        return AssessmentDraft(
            recommendation='needs_review',
            recommended_workflow_id=recommended_workflow.workflow_id,
            candidate_workflow_families=interpretation.candidate_workflow_families,
            unresolved_fields=unresolved_fields,
            blocking_reasons=blocking_reasons,
            approval_tier=approval_tier,
            assessment_notes=assessment_notes,
            status='needs_review',
        )

    assessment_notes.append('Interpretation can proceed toward design drafting.')
    return AssessmentDraft(
        recommendation='proceed',
        recommended_workflow_id=recommended_workflow.workflow_id,
        candidate_workflow_families=interpretation.candidate_workflow_families,
        unresolved_fields=[],
        blocking_reasons=blocking_reasons,
        approval_tier=approval_tier,
        assessment_notes=assessment_notes,
        status='ready_for_design',
    )


app = FastAPI(title='glasslab-assessment-agent', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status='ok', model_backend=MODEL_BACKEND.model_dump())


@app.post('/assess-interpretation', response_model=AssessmentResponse)
def assess_interpretation(request: AssessmentRequest) -> AssessmentResponse:
    return AssessmentResponse(
        request_id=request.request_id,
        draft=build_assessment_draft(request),
        model_backend=MODEL_BACKEND,
        warnings=[
            'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
        ],
    )
