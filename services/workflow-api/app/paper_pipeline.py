from __future__ import annotations

from typing import Any

from .config import Settings
from .schemas import DesignDraftRecord, FreshPaperPipelineRequest, IntakeCreateRequest, IntakeRecord, InterpretationRecord


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


def auto_resolve_pipeline_design_inputs_impl(
    design: DesignDraftRecord,
    intake: IntakeRecord,
    interpretation: InterpretationRecord,
    request: FreshPaperPipelineRequest,
    settings: Settings,
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


def auto_resolve_pipeline_design_inputs(
    design: DesignDraftRecord,
    intake: IntakeRecord,
    interpretation: InterpretationRecord,
    request: FreshPaperPipelineRequest,
    settings: Settings,
) -> tuple[dict[str, Any], list[str]]:
    return auto_resolve_pipeline_design_inputs_impl(
        design=design,
        intake=intake,
        interpretation=interpretation,
        request=request,
        settings=settings,
    )
