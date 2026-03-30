from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from .config import Settings
from .persistence import RunStore
from .registry import WorkflowRegistry
from .session_helpers import build_research_session_literature_digest
from .source_documents import ARCHITECTURE_KEYWORDS, BASELINE_KEYWORDS, DATASET_KEYWORDS, LOSS_KEYWORDS, METRIC_KEYWORDS, PYTHON_LIBRARY_KEYWORDS
from .schemas import IntakeCreateRequest, IntakeRecord, InterpretationRecord

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


def normalize_unique_strings(values: list[str]) -> list[str]:
    cleaned = [' '.join(item.split()) for item in values if item and item.strip()]
    return list(dict.fromkeys(cleaned))


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
    hints.extend(keyword for keyword in DATASET_KEYWORDS if keyword in lowered)
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
    targets.extend(keyword for keyword in METRIC_KEYWORDS if keyword in lowered)
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


def infer_recommended_method_family(candidate_workflows: list[str]) -> str | None:
    if 'generic-tabular-benchmark' in candidate_workflows:
        return 'tabular_benchmark'
    if 'replication-lite' in candidate_workflows:
        return 'lightweight_replication'
    if 'literature-to-experiment' in candidate_workflows:
        return 'literature_derived_experiment'
    return None


def infer_keyword_hints(intake: IntakeRecord, keywords: list[str]) -> list[str]:
    lowered = ' '.join([intake.raw_request, intake.normalized_summary, *intake.notes, *intake.source_refs]).lower()
    return list(dict.fromkeys(keyword for keyword in keywords if keyword in lowered))


def infer_mutation_axes(
    candidate_workflows: list[str],
    dataset_hints: list[str],
    evaluation_targets: list[str],
    architectures: list[str],
    baselines: list[str],
    losses: list[str],
) -> list[str]:
    axes: list[str] = []
    if architectures:
        axes.append('architecture choice')
    if baselines:
        axes.append('baseline inclusion')
    if losses:
        axes.append('loss/objective variant')
    if dataset_hints:
        axes.append('dataset selection')
    if evaluation_targets:
        axes.append('metric emphasis')
    if 'replication-lite' in candidate_workflows:
        axes.append('resource profile')
    return list(dict.fromkeys(axes))


def infer_gpu_required(
    recommended_architectures: list[str],
    python_packages: list[str],
    candidate_workflows: list[str],
) -> bool:
    if 'gpu-experiment' in candidate_workflows:
        return True
    gpu_packages = {'torch', 'torchvision', 'pytorch lightning', 'lightning', 'diffusers', 'accelerate', 'timm', 'tensorflow', 'jax', 'flax'}
    if any(package in gpu_packages for package in python_packages):
        return True
    gpu_architectures = {'vision transformer', 'transformer', 'cnn', 'convolutional neural network', 'unet', 'u-net', 'efficientnet', 'clip', 'gan', 'diffusion'}
    return any(item in gpu_architectures for item in recommended_architectures)


def infer_preferred_execution_surface(
    candidate_workflows: list[str],
    dataset_hints: list[str],
    gpu_required: bool,
) -> tuple[str | None, str | None]:
    if gpu_required:
        return 'gpu-experiment', 'gpu-small'
    if 'generic-tabular-benchmark' in candidate_workflows or 'titanic' in dataset_hints or 'tabular dataset' in dataset_hints:
        return 'generic-tabular-benchmark', 'cpu-small'
    if 'literature-to-experiment' in candidate_workflows:
        return 'literature-to-experiment', 'cpu-medium'
    if 'replication-lite' in candidate_workflows:
        return 'replication-lite', 'cpu-medium'
    return None, None


def build_document_context(intake: IntakeRecord, store: RunStore) -> str:
    parts: list[str] = []
    for document_id in intake.document_refs:
        record = store.get_source_document(document_id)
        if record is None:
            continue
        if record.validation_status == 'mismatch':
            continue
        label = record.title or record.expected_title or record.source_url
        detail_parts: list[str] = []
        if record.abstract_excerpt:
            detail_parts.append(f'abstract {record.abstract_excerpt}')
        elif record.text_excerpt:
            detail_parts.append(record.text_excerpt)
        if record.method_hints:
            detail_parts.append(f"methods {', '.join(record.method_hints[:3])}")
        if record.dataset_hints:
            detail_parts.append(f"datasets {', '.join(record.dataset_hints[:3])}")
        if record.metric_hints:
            detail_parts.append(f"metrics {', '.join(record.metric_hints[:3])}")
        if not detail_parts:
            detail_parts.append('source document fetched without extracted text')
        parts.append(f"{label}: {'; '.join(detail_parts)}")
    return ' '.join(parts)


def build_literature_digest_context(intake: IntakeRecord, store: RunStore) -> str:
    if not intake.session_id:
        return ''
    session = store.get_research_session(intake.session_id)
    if session is None:
        return ''
    digest = build_research_session_literature_digest(session, store)
    if not digest.summary_notes:
        return ''
    return 'Session literature digest: ' + ' '.join(digest.summary_notes[:4])


def build_interpretation_notes(intake: IntakeRecord, store: RunStore | None = None) -> list[str]:
    notes = list(intake.notes)
    if store is None:
        return notes
    digest_context = build_literature_digest_context(intake, store)
    document_context = build_document_context(intake, store)
    enriched_notes: list[str] = []
    if digest_context:
        enriched_notes.append(digest_context)
    if document_context:
        enriched_notes.append(document_context)
    return [*enriched_notes, *notes]


def infer_unresolved_questions(
    intake: IntakeRecord,
    candidates: list[str],
    dataset_hints: list[str],
    evaluation_targets: list[str],
) -> list[str]:
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
    recommended_method_family = infer_recommended_method_family(candidate_workflows)
    recommended_baselines = infer_keyword_hints(enriched_intake, BASELINE_KEYWORDS)
    recommended_architectures = infer_keyword_hints(enriched_intake, ARCHITECTURE_KEYWORDS)
    recommended_losses = infer_keyword_hints(enriched_intake, LOSS_KEYWORDS)
    recommended_python_packages = infer_keyword_hints(enriched_intake, PYTHON_LIBRARY_KEYWORDS)
    gpu_required = infer_gpu_required(recommended_architectures, recommended_python_packages, candidate_workflows)
    preferred_workflow_id, preferred_resource_profile = infer_preferred_execution_surface(
        candidate_workflows,
        dataset_hints,
        gpu_required,
    )
    mutation_axes = infer_mutation_axes(
        candidate_workflows,
        dataset_hints,
        evaluation_targets,
        recommended_architectures,
        recommended_baselines,
        recommended_losses,
    )
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
        recommended_method_family=recommended_method_family,
        recommended_datasets=dataset_hints,
        recommended_metrics=evaluation_targets,
        recommended_baselines=recommended_baselines,
        recommended_architectures=recommended_architectures,
        recommended_python_packages=recommended_python_packages,
        preferred_workflow_id=preferred_workflow_id,
        preferred_resource_profile=preferred_resource_profile,
        gpu_required=gpu_required,
        mutation_axes=mutation_axes,
        interpretation_source='deterministic',
        interpretation_backend=None,
        interpretation_warnings=[],
        unresolved_questions=unresolved_questions,
        submitted_by=intake.submitted_by,
        session_id=intake.session_id,
    )
