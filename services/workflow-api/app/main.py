from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from services.common.schemas import ArtifactIndexEntry, ArtifactsIndex, RunManifest, RunStatus, WorkflowRegistryEntry

from .config import Settings, get_settings
from .job_submission import JobSubmitter, create_job_submitter
from .persistence import InMemoryRunStore, RunStore
from .registry import WorkflowRegistry
from .schemas import (
    DesignDraftRecord,
    DesignDraftReviewRequest,
    DigestScheduleCreateRequest,
    IntakeCreateRequest,
    IntakeRecord,
    InterpretationRecord,
    LogEntry,
    ApprovedRerunScheduleCreateRequest,
    ReplicabilityAssessmentRecord,
    RunArtifactsResponse,
    RunCreateRequest,
    RunLogsResponse,
    RunRecord,
    ScheduledOperationRecord,
    WorkflowFamilySummary,
)
from .validation import validate_run_request

MEDIA_TYPES = {
    '.json': 'application/json',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.txt': 'text/plain',
    '.log': 'text/plain',
}
UNRESOLVED_PREFIX = 'UNRESOLVED_'
LOG_LINE_RE = re.compile(r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<level>[A-Z]+) (?P<logger>[^ ]+) (?P<message>.*)$')
LOGGER = logging.getLogger(__name__)


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
        raw_request=validated_draft['raw_request'],
        normalized_summary=validated_draft['normalized_summary'],
        workflow_family_candidates=validated_draft['workflow_family_candidates'],
        notes=validated_draft['notes'],
        submitted_by=validated_draft['submitted_by'],
    )


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
    request_obj = urllib_request.Request(
        settings.intake_agent_url,
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


def build_interpretation_record(intake: IntakeRecord) -> InterpretationRecord:
    now = datetime.now(timezone.utc)
    candidate_workflows = list(dict.fromkeys([workflow for workflow in intake.workflow_family_candidates if workflow]))
    dataset_hints = infer_dataset_hints(intake)
    evaluation_targets = infer_evaluation_targets(intake)
    extracted_claims = infer_extracted_claims(intake)
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
        ),
        candidate_workflow_families=candidate_workflows,
        dataset_hints=dataset_hints,
        evaluation_targets=evaluation_targets,
        extracted_claims=extracted_claims,
        unresolved_questions=unresolved_questions,
        submitted_by=intake.submitted_by,
    )


def normalize_unique_strings(values: list[str]) -> list[str]:
    cleaned = [' '.join(item.split()) for item in values if item and item.strip()]
    return list(dict.fromkeys(cleaned))


def validate_interpretation_agent_draft(
    draft: dict[str, Any],
    intake: IntakeRecord,
    registry: WorkflowRegistry,
) -> dict[str, Any]:
    required_string_fields = ('source_type', 'normalized_summary', 'extracted_method_summary')
    for field_name in required_string_fields:
        value = draft.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'interpretation agent draft missing valid {field_name}')

    normalized = {
        'source_type': draft['source_type'].strip(),
        'normalized_summary': ' '.join(draft['normalized_summary'].split())[:500],
        'extracted_method_summary': ' '.join(draft['extracted_method_summary'].split())[:500],
        'candidate_workflow_families': normalize_unique_strings(list(draft.get('candidate_workflow_families', []))),
        'dataset_hints': normalize_unique_strings(list(draft.get('dataset_hints', []))),
        'evaluation_targets': normalize_unique_strings(list(draft.get('evaluation_targets', []))),
        'extracted_claims': normalize_unique_strings(list(draft.get('extracted_claims', [])))[:3],
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
        candidate_workflow_families=validated_draft['candidate_workflow_families'],
        dataset_hints=validated_draft['dataset_hints'],
        evaluation_targets=validated_draft['evaluation_targets'],
        extracted_claims=validated_draft['extracted_claims'],
        unresolved_questions=unresolved_questions,
        submitted_by=intake.submitted_by,
    )


def call_interpretation_agent(
    intake: IntakeRecord,
    settings: Settings,
    registry: WorkflowRegistry,
) -> InterpretationRecord | None:
    if not settings.interpretation_agent_enabled:
        return None

    payload = {
        'request_id': intake.intake_id,
        'intake': {
            'intake_id': intake.intake_id,
            'source_type': intake.source_type,
            'source_refs': intake.source_refs,
            'raw_request': intake.raw_request,
            'normalized_summary': intake.normalized_summary,
            'workflow_family_candidates': intake.workflow_family_candidates,
            'notes': intake.notes,
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

    if recommended_workflow is not None:
        approval_tier = recommended_workflow.approval_tier
        assessment_notes.append(
            f"Best current approved workflow match is {recommended_workflow.workflow_id}."
        )
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
    )


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


def compute_unresolved_inputs(declared_inputs: dict[str, Any]) -> list[str]:
    return [
        name for name, value in declared_inputs.items() if isinstance(value, str) and value.startswith(UNRESOLVED_PREFIX)
    ]


def build_design_draft(
    intake: IntakeRecord,
    workflow: WorkflowRegistryEntry,
    submitted_by: str,
    source_assessment_id: str | None = None,
) -> DesignDraftRecord:
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


def build_digest_schedule(request: DigestScheduleCreateRequest, settings: Settings) -> ScheduledOperationRecord:
    now = datetime.now(timezone.utc)
    return ScheduledOperationRecord(
        schedule_id=uuid4().hex,
        created_at=now,
        updated_at=now,
        status='active',
        operation_type='digest',
        approval_tier='tier-1-read-only',
        owner=request.owner or settings.default_submitted_by,
        cron_expr=request.cron_expr.strip(),
        scope_filter=request.scope_filter,
        digest_kind=request.digest_kind.strip(),
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


def disable_schedule(record: ScheduledOperationRecord) -> ScheduledOperationRecord:
    now = datetime.now(timezone.utc)
    return record.model_copy(
        update={
            'status': 'disabled',
            'updated_at': now,
            'last_result_status': record.last_result_status or 'disabled',
            'last_result_detail': record.last_result_detail or 'Disabled by operator action.',
        }
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


def artifact_run_dir(settings: Settings, run_id: str) -> Path:
    return Path(settings.artifacts_mount_path) / run_id


def load_status_from_disk(settings: Settings, run_id: str) -> RunStatus | None:
    path = artifact_run_dir(settings, run_id) / 'status.json'
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return RunStatus.model_validate(payload)


def build_artifacts_from_directory(settings: Settings, run_id: str) -> ArtifactsIndex | None:
    root = artifact_run_dir(settings, run_id)
    if not root.exists():
        return None
    artifacts: list[ArtifactIndexEntry] = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            artifacts.append(
                ArtifactIndexEntry(
                    name=f'{relative}/',
                    path=f'artifacts/{run_id}/{relative}/',
                    media_type='inode/directory',
                    required=relative == 'logs',
                    description='Discovered from shared artifacts volume',
                )
            )
            continue
        artifacts.append(
            ArtifactIndexEntry(
                name=relative,
                path=f'artifacts/{run_id}/{relative}',
                media_type=MEDIA_TYPES.get(path.suffix.lower(), 'application/octet-stream'),
                required=relative in {'run_manifest.json', 'config.json', 'metrics.json', 'artifacts_index.json', 'report.md', 'status.json', 'logs/runner.log'},
                size_bytes=path.stat().st_size,
                description='Discovered from shared artifacts volume',
            )
        )
    return ArtifactsIndex(run_id=run_id, artifacts=artifacts)


def load_artifacts_from_disk(settings: Settings, run_id: str) -> ArtifactsIndex | None:
    index_path = artifact_run_dir(settings, run_id) / 'artifacts_index.json'
    if index_path.exists():
        payload = json.loads(index_path.read_text())
        return ArtifactsIndex.model_validate(payload)
    return build_artifacts_from_directory(settings, run_id)


def parse_log_line(line: str) -> LogEntry:
    match = LOG_LINE_RE.match(line)
    if not match:
        return LogEntry(timestamp=datetime.now(timezone.utc), level='INFO', message=line)
    timestamp = datetime.strptime(match.group('ts'), '%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=timezone.utc)
    return LogEntry(timestamp=timestamp, level=match.group('level'), message=match.group('message'), payload={'logger': match.group('logger')})


def load_logs_from_disk(settings: Settings, run_id: str) -> list[LogEntry]:
    log_path = artifact_run_dir(settings, run_id) / 'logs' / 'runner.log'
    if not log_path.exists():
        return []
    return [parse_log_line(line) for line in log_path.read_text().splitlines() if line.strip()]


def resolve_run_status(record: RunRecord, settings: Settings, submitter: JobSubmitter) -> RunStatus:
    disk_status = load_status_from_disk(settings, record.run_id)
    if disk_status is not None:
        return disk_status
    live_status = submitter.get_live_status(record)
    if live_status is not None:
        return live_status
    return record.status


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
        record = call_intake_agent(request, settings, registry)
        if record is None:
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

    @app.post('/interpretations/from-latest-intake', response_model=InterpretationRecord, status_code=status.HTTP_201_CREATED)
    def create_interpretation_from_latest_intake() -> InterpretationRecord:
        intake = store.get_latest_intake()
        if intake is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='intake not found')
        record = call_interpretation_agent(intake, settings, registry) or build_interpretation_record(intake)
        store.save_interpretation(record)
        return record

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

    @app.post(
        '/replicability-assessments/from-latest-interpretation',
        response_model=ReplicabilityAssessmentRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_replicability_assessment_from_latest_interpretation() -> ReplicabilityAssessmentRecord:
        interpretation = store.get_latest_interpretation()
        if interpretation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='interpretation not found')
        record = build_replicability_assessment(interpretation, registry)
        store.save_replicability_assessment(record)
        return record

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
        workflow = registry.get_workflow(assessment.recommended_workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        record = build_design_draft(
            intake,
            workflow,
            submitted_by=assessment.submitted_by,
            source_assessment_id=assessment.assessment_id,
        )
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

    @app.post('/design-drafts/latest/review', response_model=DesignDraftRecord)
    def review_latest_design_draft(request: DesignDraftReviewRequest) -> DesignDraftRecord:
        record = store.get_latest_design_draft()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        updated = review_design_draft(record, request)
        store.save_design_draft(updated)
        return updated

    @app.post('/design-drafts/{design_id}/review', response_model=DesignDraftRecord)
    def review_existing_design_draft(design_id: str, request: DesignDraftReviewRequest) -> DesignDraftRecord:
        record = store.get_design_draft(design_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        updated = review_design_draft(record, request)
        store.save_design_draft(updated)
        return updated

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
