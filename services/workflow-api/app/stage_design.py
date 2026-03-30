from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from services.common.schemas import WorkflowRegistryEntry

from .config import Settings
from .registry import WorkflowRegistry
from .schemas import DesignDraftRecord, IntakeRecord, InterpretationRecord, ReplicabilityAssessmentRecord
from .stage_inference import normalize_unique_strings

LOGGER = logging.getLogger(__name__)
UNRESOLVED_PREFIX = 'UNRESOLVED_'


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
        validated_draft = validate_assessment_agent_draft(draft, registry)
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
                'validation_strategy': 'holdout',
                'validation_split': '0.2',
                'target_column': 'Survived',
            }
            design_notes.append('Resolved approved Titanic benchmark inputs deterministically.')
            design_notes.append('Declared holdout validation strategy with a 0.2 validation split to help guard against overfitting.')
        else:
            declared_inputs = {
                'dataset_name': 'UNRESOLVED_DATASET_NAME',
                'train_uri': 'UNRESOLVED_TRAIN_URI',
                'test_uri': 'UNRESOLVED_TEST_URI',
                'validation_strategy': 'UNRESOLVED_VALIDATION_STRATEGY',
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
        candidate_models=workflow.allowed_models[:2],
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

    return {
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
