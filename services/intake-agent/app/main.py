from __future__ import annotations

import re

from fastapi import FastAPI

from .models import (
    HealthResponse,
    ModelBackendMetadata,
    NormalizeIntakeRequest,
    NormalizeIntakeResponse,
    NormalizedIntakeDraft,
)

TOKEN_RE = re.compile(r"[a-z0-9]+")

MODEL_BACKEND = ModelBackendMetadata(
    provider='ollama',
    base_url='http://192.168.1.23:11434',
    model='qwen3:30b',
    timeout_seconds=30.0,
)


def summarize_intake(raw_request: str, notes: list[str]) -> str:
    summary = ' '.join(raw_request.split())
    if notes:
        note_preview = '; '.join(' '.join(item.split()) for item in notes[:2])
        summary = f'{summary} Notes: {note_preview}'
    return summary[:500]


def infer_source_type(raw_request: str, source_refs: list[str], source_type: str | None) -> str:
    if source_type:
        return source_type.strip()
    if any(ref.startswith(('http://', 'https://')) for ref in source_refs):
        return 'paper-link'
    lowered = raw_request.lower()
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


def build_normalized_draft(request: NormalizeIntakeRequest) -> NormalizedIntakeDraft:
    intake = request.intake
    return NormalizedIntakeDraft(
        source_type=infer_source_type(intake.raw_request, intake.source_refs, intake.source_type),
        source_refs=intake.source_refs,
        raw_request=intake.raw_request.strip(),
        normalized_summary=summarize_intake(intake.raw_request, intake.notes),
        workflow_family_candidates=infer_workflow_candidates(intake.raw_request),
        notes=intake.notes,
        submitted_by=intake.submitted_by or 'glasslab-operator',
    )


app = FastAPI(title='glasslab-intake-agent', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status='ok', model_backend=MODEL_BACKEND.model_dump())


@app.post('/normalize-intake', response_model=NormalizeIntakeResponse)
def normalize_intake(request: NormalizeIntakeRequest) -> NormalizeIntakeResponse:
    return NormalizeIntakeResponse(
        request_id=request.request_id,
        draft=build_normalized_draft(request),
        model_backend=MODEL_BACKEND,
        warnings=[
            'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
        ],
    )
