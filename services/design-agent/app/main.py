from __future__ import annotations

from fastapi import FastAPI

from .models import DesignDraft, DesignRequest, DesignResponse, HealthResponse, ModelBackendMetadata

UNRESOLVED_PREFIX = 'UNRESOLVED_'

MODEL_BACKEND = ModelBackendMetadata(
    provider='ollama',
    base_url='http://192.168.1.23:11434',
    model='qwen3:30b',
    timeout_seconds=45.0,
)


def derive_design_from_intake(request: DesignRequest) -> tuple[dict[str, object], list[str], list[str]]:
    intake = request.intake
    workflow = request.workflow
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    declared_inputs: dict[str, object] = {}
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


def build_design_draft(request: DesignRequest) -> DesignDraft:
    intake = request.intake
    workflow = request.workflow
    declared_inputs, unresolved_inputs, design_notes = derive_design_from_intake(request)
    if workflow.approval_tier != 'tier-2-approved-execution':
        design_notes.append(f'Approval tier {workflow.approval_tier} requires operator review before run creation.')
    return DesignDraft(
        workflow_id=workflow.workflow_id,
        workflow_family=workflow.workflow_family,
        objective=f'Derived from intake: {intake.normalized_summary}'[:500],
        declared_inputs=declared_inputs,
        unresolved_inputs=unresolved_inputs,
        candidate_models=workflow.allowed_models[:2],
        resource_profile=workflow.resource_profile_name,
        expected_artifacts=workflow.expected_artifacts,
        approval_tier=workflow.approval_tier,
        design_notes=design_notes,
    )


app = FastAPI(title='glasslab-design-agent', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status='ok', model_backend=MODEL_BACKEND.model_dump())


@app.post('/draft-design', response_model=DesignResponse)
def draft_design(request: DesignRequest) -> DesignResponse:
    return DesignResponse(
        request_id=request.request_id,
        draft=build_design_draft(request),
        model_backend=MODEL_BACKEND,
        warnings=[
            'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
        ],
    )
