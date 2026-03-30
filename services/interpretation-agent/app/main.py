from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
import re
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI

from .models import (
    HealthResponse,
    InterpretationDraft,
    InterpretationRequest,
    InterpretationResponse,
    ModelBackendMetadata,
)

TOKEN_RE = re.compile(r"[a-z0-9]+")

WORKFLOW_HINTS: dict[str, set[str]] = {
    'literature-to-experiment': {'paper', 'literature', 'claim', 'method', 'study', 'review'},
    'generic-tabular-benchmark': {'tabular', 'benchmark', 'dataset', 'csv', 'train', 'test', 'titanic'},
    'replication-lite': {'replicate', 'replication', 'reproduce', 'repeat', 'rerun'},
    'gpu-experiment': {'gpu', 'vision', 'transformer', 'pytorch', 'torch', 'timm', 'image'},
}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    model: str
    timeout_seconds: float

    def metadata(self) -> ModelBackendMetadata:
        return ModelBackendMetadata(
            provider=self.provider,
            base_url=self.base_url,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
        )

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip('/') + '/api/chat'


PRIMARY_BACKEND = ProviderConfig(
    provider=os.getenv('GLASSLAB_INTERPRETATION_AGENT_PROVIDER_API', 'ollama').strip() or 'ollama',
    base_url=os.getenv('GLASSLAB_INTERPRETATION_AGENT_PROVIDER_BASE_URL', 'http://192.168.1.23:11434').strip(),
    model=os.getenv('GLASSLAB_INTERPRETATION_AGENT_MODEL', 'qwen3:30b').strip() or 'qwen3:30b',
    timeout_seconds=float(os.getenv('GLASSLAB_INTERPRETATION_AGENT_TIMEOUT_SECONDS', '45').strip() or '45'),
)

FALLBACK_BACKEND = ProviderConfig(
    provider=os.getenv('GLASSLAB_INTERPRETATION_AGENT_FALLBACK_PROVIDER_API', 'ollama').strip() or 'ollama',
    base_url=os.getenv('GLASSLAB_INTERPRETATION_AGENT_FALLBACK_PROVIDER_BASE_URL', 'http://192.168.1.12:11434').strip(),
    model=os.getenv('GLASSLAB_INTERPRETATION_AGENT_FALLBACK_MODEL', 'qwen3:14b').strip() or 'qwen3:14b',
    timeout_seconds=float(os.getenv('GLASSLAB_INTERPRETATION_AGENT_FALLBACK_TIMEOUT_SECONDS', '30').strip() or '30'),
)

MODEL_BACKEND = PRIMARY_BACKEND.metadata()

SYSTEM_PROMPT = """You are the bounded Glasslab interpretation agent.
Return exactly one JSON object matching the requested schema.
Do not propose arbitrary code execution.
Prefer approved workflow families already present in the candidate list.
Only infer GPU execution when the source clearly suggests it.
Keep lists short, unique, and concrete."""


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(value.lower())


def normalize_unique_strings(values: list[str], limit: int | None = None) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = ' '.join(str(value).split())
        if not normalized:
            continue
        if normalized not in cleaned:
            cleaned.append(normalized)
        if limit is not None and len(cleaned) >= limit:
            break
    return cleaned


def infer_candidate_workflows(raw_text: str, candidates: list[str]) -> list[str]:
    counts = Counter(tokenize(raw_text))
    lowered = raw_text.lower()
    scored: list[tuple[int, str]] = []
    for workflow_id in candidates:
        hints = WORKFLOW_HINTS.get(workflow_id, set())
        score = sum(counts[token] for token in hints)
        if workflow_id == 'generic-tabular-benchmark' and any(
            token in lowered for token in ('titanic', 'tabular', 'dataset', 'csv')
        ):
            score += 3
        if workflow_id == 'replication-lite' and any(
            token in lowered for token in ('replicate', 'replication', 'reproduce', 'repeat', 'rerun')
        ):
            score += 2
        if workflow_id == 'gpu-experiment' and any(
            token in lowered for token in ('gpu', 'vision', 'transformer', 'pytorch', 'torch', 'timm', 'cuda')
        ):
            score += 3
        scored.append((score, workflow_id))
    ranked = [workflow_id for score, workflow_id in sorted(scored, key=lambda item: (-item[0], item[1])) if score > 0]
    remainder = [workflow_id for workflow_id in candidates if workflow_id not in ranked]
    return ranked + remainder


def infer_dataset_hints(raw_text: str) -> list[str]:
    lowered = raw_text.lower()
    hints: list[str] = []
    if 'titanic' in lowered:
        hints.append('titanic')
    if 'csv' in lowered:
        hints.append('csv-backed dataset')
    if 'tabular' in lowered:
        hints.append('tabular dataset')
    if 'kaggle' in lowered:
        hints.append('kaggle')
    if any(token in lowered for token in ('imagenet', 'imageforensics', 'deepfake', 'forgery')):
        hints.append('image benchmark')
    return hints


def infer_evaluation_targets(raw_text: str) -> list[str]:
    lowered = raw_text.lower()
    targets: list[str] = []
    if any(token in lowered for token in ('baseline', 'benchmark', 'compare')):
        targets.append('baseline comparison')
    if any(token in lowered for token in ('accuracy', 'auc', 'metric')):
        targets.append('reported metrics')
    if any(token in lowered for token in ('iou', 'f1', 'precision', 'recall')):
        targets.append('paper-claimed evaluation')
    if 'survived' in lowered:
        targets.append('Survived prediction target')
    if not targets and 'paper' in lowered:
        targets.append('paper-claimed evaluation')
    return targets


def infer_claims(notes: list[str], normalized_summary: str) -> list[str]:
    claims = [' '.join(item.split())[:240] for item in notes if item.strip()]
    if not claims:
        claims.append(normalized_summary[:240])
    return claims[:3]


def infer_literature_state_summary(raw_text: str, normalized_summary: str) -> str:
    cleaned = ' '.join(raw_text.split())
    if cleaned:
        return f'Current bounded literature view: {cleaned[:420]}'
    return f'Current bounded literature view is based on the intake summary: {normalized_summary[:420]}'


def infer_research_gaps(
    raw_text: str,
    source_type: str,
    source_refs: list[str],
    document_refs: list[str],
    dataset_hints: list[str],
    evaluation_targets: list[str],
) -> list[str]:
    lowered = raw_text.lower()
    gaps: list[str] = []
    if not dataset_hints:
        gaps.append('The literature snapshot does not settle on one concrete dataset for a bounded run.')
    if not evaluation_targets:
        gaps.append('The literature snapshot does not identify one canonical evaluation target or metric.')
    if 'baseline' not in lowered and 'benchmark' not in lowered:
        gaps.append('Baseline comparison expectations are still underspecified in the current literature context.')
    if source_type == 'paper-link' and source_refs and not document_refs:
        gaps.append('A stored source document is missing, so interpretation still depends on URL-level context only.')
    return list(dict.fromkeys(gaps))[:4]


def infer_bounded_experiment_ideas(candidate_workflows: list[str], dataset_hints: list[str]) -> list[str]:
    ideas: list[str] = []
    if 'generic-tabular-benchmark' in candidate_workflows:
        dataset_label = dataset_hints[0] if dataset_hints else 'one approved tabular dataset'
        ideas.append(
            f'Run a bounded benchmark on {dataset_label} and compare the reported baseline against approved local baselines.'
        )
    if 'literature-to-experiment' in candidate_workflows:
        ideas.append('Convert the reported method into a minimal literature-derived experiment with one dataset and one evaluation target.')
    if 'replication-lite' in candidate_workflows:
        ideas.append('Attempt a lightweight replication of the core reported claim with a reduced approved configuration.')
    if 'gpu-experiment' in candidate_workflows:
        ideas.append('Stage one GPU-backed validation run with a constrained package set and one primary metric.')
    return list(dict.fromkeys(ideas))[:3]


def infer_runtime_hints(
    raw_text: str,
    candidate_workflows: list[str],
    dataset_hints: list[str],
    evaluation_targets: list[str],
) -> dict[str, Any]:
    lowered = raw_text.lower()
    packages: list[str] = []
    if any(token in lowered for token in ('pytorch', 'torch')):
        packages.append('torch')
    if 'timm' in lowered:
        packages.append('timm')
    if 'torchvision' in lowered:
        packages.append('torchvision')
    if any(token in lowered for token in ('sklearn', 'scikit-learn')):
        packages.append('scikit-learn')
    if 'xgboost' in lowered:
        packages.append('xgboost')
    if 'catboost' in lowered:
        packages.append('catboost')

    architectures: list[str] = []
    if any(token in lowered for token in ('transformer', 'vit')):
        architectures.append('transformer')
    if 'cnn' in lowered:
        architectures.append('cnn')
    if 'xgboost' in lowered:
        architectures.append('gradient-boosted trees')

    baselines: list[str] = []
    if 'baseline' in lowered:
        baselines.append('reported baseline')
    if 'compare' in lowered and 'scikit-learn' in packages:
        baselines.append('scikit-learn baseline')

    metrics: list[str] = []
    if 'accuracy' in lowered:
        metrics.append('accuracy')
    if 'f1' in lowered:
        metrics.append('f1')
    if 'iou' in lowered:
        metrics.append('iou')
    if not metrics:
        metrics = evaluation_targets[:2]

    recommended_method_family = None
    if 'gpu-experiment' in candidate_workflows:
        recommended_method_family = 'gpu-backed methodology validation'
    elif 'generic-tabular-benchmark' in candidate_workflows:
        recommended_method_family = 'tabular benchmark comparison'
    elif 'replication-lite' in candidate_workflows:
        recommended_method_family = 'lightweight replication'

    preferred_workflow_id = candidate_workflows[0] if candidate_workflows else None
    preferred_resource_profile = 'cpu-medium'
    gpu_required = False
    if preferred_workflow_id == 'gpu-experiment' or any(token in lowered for token in ('gpu', 'cuda', 'vision', 'transformer', 'vit')):
        preferred_workflow_id = 'gpu-experiment'
        preferred_resource_profile = 'gpu-small'
        gpu_required = True
    elif preferred_workflow_id == 'generic-tabular-benchmark':
        preferred_resource_profile = 'cpu-small'

    mutation_axes: list[str] = []
    if architectures:
        mutation_axes.append('architecture choice')
    if baselines:
        mutation_axes.append('baseline inclusion')
    if metrics:
        mutation_axes.append('metric emphasis')
    if dataset_hints:
        mutation_axes.append('dataset split strategy')
    if gpu_required:
        mutation_axes.append('resource profile')

    return {
        'recommended_method_family': recommended_method_family,
        'recommended_datasets': dataset_hints[:4],
        'recommended_metrics': metrics[:4],
        'recommended_baselines': baselines[:4],
        'recommended_architectures': architectures[:4],
        'recommended_python_packages': packages[:6],
        'preferred_workflow_id': preferred_workflow_id,
        'preferred_resource_profile': preferred_resource_profile,
        'gpu_required': gpu_required,
        'mutation_axes': mutation_axes[:6],
    }


def infer_unresolved_questions(
    source_type: str,
    candidate_workflows: list[str],
    dataset_hints: list[str],
    evaluation_targets: list[str],
    source_refs: list[str],
) -> list[str]:
    unresolved: list[str] = []
    if not candidate_workflows:
        unresolved.append('Which approved workflow family should this request map to?')
    if not dataset_hints:
        unresolved.append('Which concrete dataset should the backend use?')
    if not evaluation_targets:
        unresolved.append('Which evaluation target or metric should be treated as canonical?')
    if source_type == 'paper-link' and not source_refs:
        unresolved.append('Which source reference should be treated as canonical for this paper intake?')
    return unresolved


def build_interpretation_draft(request: InterpretationRequest) -> InterpretationDraft:
    intake = request.intake
    raw_text = ' '.join(
        [
            intake.raw_request,
            intake.normalized_summary,
            *intake.notes,
            *intake.source_refs,
        ]
    )
    candidate_workflows = infer_candidate_workflows(raw_text, intake.workflow_family_candidates)
    dataset_hints = infer_dataset_hints(raw_text)
    evaluation_targets = infer_evaluation_targets(raw_text)
    extracted_claims = infer_claims(intake.notes, intake.normalized_summary)
    literature_state_summary = infer_literature_state_summary(raw_text, intake.normalized_summary)
    research_gaps = infer_research_gaps(
        raw_text,
        intake.source_type,
        intake.source_refs,
        intake.document_refs,
        dataset_hints,
        evaluation_targets,
    )
    bounded_experiment_ideas = infer_bounded_experiment_ideas(candidate_workflows, dataset_hints)
    unresolved_questions = infer_unresolved_questions(
        intake.source_type,
        candidate_workflows,
        dataset_hints,
        evaluation_targets,
        intake.source_refs,
    )
    runtime_hints = infer_runtime_hints(raw_text, candidate_workflows, dataset_hints, evaluation_targets)
    return InterpretationDraft(
        source_type=intake.source_type,
        normalized_summary=intake.normalized_summary,
        extracted_method_summary=(
            f"Interpreted intake as {', '.join(candidate_workflows) or 'unmapped research work'} "
            f"with source type {intake.source_type}."
        ),
        literature_state_summary=literature_state_summary,
        candidate_workflow_families=candidate_workflows,
        dataset_hints=dataset_hints,
        evaluation_targets=evaluation_targets,
        extracted_claims=extracted_claims,
        research_gaps=research_gaps,
        bounded_experiment_ideas=bounded_experiment_ideas,
        unresolved_questions=unresolved_questions,
        **runtime_hints,
    )


def build_prompt_payload(request: InterpretationRequest, deterministic_draft: InterpretationDraft) -> dict[str, Any]:
    intake = request.intake
    allowed_workflows = intake.workflow_family_candidates
    schema_keys = {
        'source_type': 'string',
        'normalized_summary': 'string',
        'extracted_method_summary': 'string',
        'literature_state_summary': 'string',
        'candidate_workflow_families': 'string[]',
        'dataset_hints': 'string[]',
        'evaluation_targets': 'string[]',
        'extracted_claims': 'string[]',
        'research_gaps': 'string[]',
        'bounded_experiment_ideas': 'string[]',
        'recommended_method_family': 'string|null',
        'recommended_datasets': 'string[]',
        'recommended_metrics': 'string[]',
        'recommended_baselines': 'string[]',
        'recommended_architectures': 'string[]',
        'recommended_python_packages': 'string[]',
        'preferred_workflow_id': 'string|null',
        'preferred_resource_profile': 'string|null',
        'gpu_required': 'boolean',
        'mutation_axes': 'string[]',
        'unresolved_questions': 'string[]',
    }
    user_payload = {
        'request_id': request.request_id,
        'allowed_workflow_families': allowed_workflows,
        'intake': intake.model_dump(),
        'deterministic_baseline': deterministic_draft.model_dump(),
        'required_output_schema': schema_keys,
        'rules': [
            'Return only one JSON object and no markdown.',
            'Do not include any keys outside the required schema.',
            'Use only workflow ids from allowed_workflow_families.',
            'Infer GPU execution only when the intake strongly supports it.',
            'Keep lists unique and short.',
        ],
    }
    return {
        'model': '',
        'stream': False,
        'format': 'json',
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(user_payload, ensure_ascii=True)},
        ],
        'options': {
            'temperature': 0.1,
        },
    }


def normalize_model_draft(raw_draft: dict[str, Any], request: InterpretationRequest) -> InterpretationDraft:
    baseline = build_interpretation_draft(request)
    payload = baseline.model_dump()
    for key, value in raw_draft.items():
        if key not in payload:
            continue
        payload[key] = value

    for list_field, limit in (
        ('candidate_workflow_families', 4),
        ('dataset_hints', 4),
        ('evaluation_targets', 4),
        ('extracted_claims', 3),
        ('research_gaps', 4),
        ('bounded_experiment_ideas', 3),
        ('recommended_datasets', 4),
        ('recommended_metrics', 4),
        ('recommended_baselines', 4),
        ('recommended_architectures', 4),
        ('recommended_python_packages', 6),
        ('mutation_axes', 6),
        ('unresolved_questions', 6),
    ):
        payload[list_field] = normalize_unique_strings(list(payload.get(list_field, [])), limit=limit)

    if payload['candidate_workflow_families']:
        allowed = set(request.intake.workflow_family_candidates)
        payload['candidate_workflow_families'] = [
            workflow_id for workflow_id in payload['candidate_workflow_families'] if workflow_id in allowed
        ]
        if not payload['candidate_workflow_families']:
            payload['candidate_workflow_families'] = baseline.candidate_workflow_families

    preferred_workflow_id = ' '.join(str(payload.get('preferred_workflow_id', '')).split()) or None
    if preferred_workflow_id and preferred_workflow_id not in request.intake.workflow_family_candidates:
        preferred_workflow_id = baseline.preferred_workflow_id
    payload['preferred_workflow_id'] = preferred_workflow_id

    payload['source_type'] = ' '.join(str(payload['source_type']).split()) or baseline.source_type
    payload['normalized_summary'] = ' '.join(str(payload['normalized_summary']).split())[:500] or baseline.normalized_summary
    payload['extracted_method_summary'] = (
        ' '.join(str(payload['extracted_method_summary']).split())[:500] or baseline.extracted_method_summary
    )
    payload['literature_state_summary'] = (
        ' '.join(str(payload['literature_state_summary']).split())[:500] or baseline.literature_state_summary
    )
    payload['recommended_method_family'] = (
        ' '.join(str(payload.get('recommended_method_family') or '').split())[:120] or None
    )
    payload['preferred_resource_profile'] = (
        ' '.join(str(payload.get('preferred_resource_profile') or '').split())[:120] or None
    )
    payload['gpu_required'] = bool(payload.get('gpu_required', False))
    return InterpretationDraft(**payload)


def parse_chat_response(body: dict[str, Any], request: InterpretationRequest) -> InterpretationDraft:
    message = body.get('message')
    if not isinstance(message, dict):
        raise ValueError('ollama response missing message object')
    content = message.get('content')
    if not isinstance(content, str) or not content.strip():
        raise ValueError('ollama response missing message content')
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError('ollama response did not return a JSON object')
    return normalize_model_draft(raw, request)


def call_backend(request: InterpretationRequest, backend: ProviderConfig) -> InterpretationDraft:
    deterministic_draft = build_interpretation_draft(request)
    payload = build_prompt_payload(request, deterministic_draft)
    payload['model'] = backend.model
    request_obj = urllib_request.Request(
        backend.chat_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib_request.urlopen(request_obj, timeout=backend.timeout_seconds) as response:
        body = json.loads(response.read().decode('utf-8'))
    return parse_chat_response(body, request)


def interpret_with_backends(request: InterpretationRequest) -> tuple[InterpretationDraft, ModelBackendMetadata, list[str]]:
    warnings: list[str] = []
    try:
        draft = call_backend(request, PRIMARY_BACKEND)
        return draft, PRIMARY_BACKEND.metadata(), warnings
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        warnings.append(f'primary interpretation backend failed: {exc}')

    try:
        draft = call_backend(request, FALLBACK_BACKEND)
        warnings.append('used fallback interpretation backend')
        return draft, FALLBACK_BACKEND.metadata(), warnings
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        warnings.append(f'fallback interpretation backend failed: {exc}')

    warnings.append('all model backends failed; using deterministic interpretation scaffold')
    return build_interpretation_draft(request), PRIMARY_BACKEND.metadata(), warnings


app = FastAPI(title='glasslab-interpretation-agent', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status='ok', model_backend=MODEL_BACKEND.model_dump())


@app.post('/interpret-intake', response_model=InterpretationResponse)
def interpret_intake(request: InterpretationRequest) -> InterpretationResponse:
    draft, backend, warnings = interpret_with_backends(request)
    return InterpretationResponse(
        request_id=request.request_id,
        draft=draft,
        model_backend=backend,
        warnings=warnings,
    )
