from __future__ import annotations

from collections import Counter
import re

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
}

MODEL_BACKEND = ModelBackendMetadata(
    provider='ollama',
    base_url='http://192.168.1.23:11434',
    model='qwen3:30b',
    timeout_seconds=45.0,
)


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(value.lower())


def infer_candidate_workflows(raw_text: str, candidates: list[str]) -> list[str]:
    counts = Counter(tokenize(raw_text))
    lowered = raw_text.lower()
    scored: list[tuple[int, str]] = []
    for workflow_id in candidates:
        hints = WORKFLOW_HINTS.get(workflow_id, set())
        score = sum(counts[token] for token in hints)
        if workflow_id == 'generic-tabular-benchmark' and any(token in lowered for token in ('titanic', 'tabular', 'dataset', 'csv')):
            score += 3
        if workflow_id == 'replication-lite' and any(token in lowered for token in ('replicate', 'replication', 'reproduce', 'repeat', 'rerun')):
            score += 2
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
    return hints


def infer_evaluation_targets(raw_text: str) -> list[str]:
    lowered = raw_text.lower()
    targets: list[str] = []
    if any(token in lowered for token in ('baseline', 'benchmark', 'compare')):
        targets.append('baseline comparison')
    if any(token in lowered for token in ('accuracy', 'auc', 'metric')):
        targets.append('reported metrics')
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
    unresolved_questions = infer_unresolved_questions(
        intake.source_type,
        candidate_workflows,
        dataset_hints,
        evaluation_targets,
        intake.source_refs,
    )
    return InterpretationDraft(
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
    )


app = FastAPI(title='glasslab-interpretation-agent', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status='ok', model_backend=MODEL_BACKEND.model_dump())


@app.post('/interpret-intake', response_model=InterpretationResponse)
def interpret_intake(request: InterpretationRequest) -> InterpretationResponse:
    warnings: list[str] = [
        'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
    ]
    return InterpretationResponse(
        request_id=request.request_id,
        draft=build_interpretation_draft(request),
        model_backend=MODEL_BACKEND,
        warnings=warnings,
    )
