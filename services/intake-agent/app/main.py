from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlparse

import yaml

from fastapi import FastAPI

from .models import (
    ApprovedSourcesSummary,
    HealthResponse,
    ModelBackendMetadata,
    NormalizeIntakeRequest,
    NormalizeIntakeResponse,
    NormalizedIntakeDraft,
)

TOKEN_RE = re.compile(r"[a-z0-9]+")
SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_MANIFEST = SERVICE_ROOT / 'seeds' / 'glasslab_paper_harvester_seed_manifest.yaml'

MODEL_BACKEND = ModelBackendMetadata(
    provider='ollama',
    base_url='http://192.168.1.23:11434',
    model='qwen3:30b',
    timeout_seconds=30.0,
)


def normalize_host(value: str) -> str | None:
    parsed = urlparse(value)
    host = parsed.netloc.strip().lower()
    if not host:
        return None
    if host.startswith('www.'):
        host = host[4:]
    return host or None


@lru_cache(maxsize=1)
def load_approved_sources_summary() -> ApprovedSourcesSummary:
    manifest = yaml.safe_load(DEFAULT_SEED_MANIFEST.read_text())
    hosts: list[str] = []
    for venue in manifest.get('venue_allowlist', []):
        homepage = venue.get('homepage')
        if isinstance(homepage, str):
            host = normalize_host(homepage)
            if host:
                hosts.append(host)
    approved_hosts = sorted(dict.fromkeys(hosts))
    return ApprovedSourcesSummary(
        manifest_name=str(manifest.get('name', 'unknown-manifest')),
        manifest_version=int(manifest.get('manifest_version', 0)),
        venue_count=len(manifest.get('venue_allowlist', [])),
        paper_count=len(manifest.get('papers', [])),
        track_query_count=len(manifest.get('track_queries', [])),
        approved_hosts=approved_hosts,
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


def build_approval_warnings(request: NormalizeIntakeRequest) -> list[str]:
    intake = request.intake
    warnings: list[str] = [
        'current implementation is deterministic scaffold logic; live model integration is not enabled yet',
    ]
    approved_sources = load_approved_sources_summary()
    if not intake.source_refs:
        return warnings

    out_of_policy_hosts: list[str] = []
    for ref in intake.source_refs:
        host = normalize_host(ref)
        if not host:
            continue
        if host not in approved_sources.approved_hosts:
            out_of_policy_hosts.append(host)
    deduped = list(dict.fromkeys(out_of_policy_hosts))
    if deduped:
        warnings.append(
            'source refs include hosts outside the current approved seed manifest: '
            + ', '.join(deduped)
        )
    return warnings


app = FastAPI(title='glasslab-intake-agent', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        status='ok',
        model_backend=MODEL_BACKEND.model_dump(),
        approved_sources=load_approved_sources_summary(),
    )


@app.get('/approved-sources', response_model=ApprovedSourcesSummary)
def approved_sources() -> ApprovedSourcesSummary:
    return load_approved_sources_summary()


@app.post('/normalize-intake', response_model=NormalizeIntakeResponse)
def normalize_intake(request: NormalizeIntakeRequest) -> NormalizeIntakeResponse:
    return NormalizeIntakeResponse(
        request_id=request.request_id,
        draft=build_normalized_draft(request),
        model_backend=MODEL_BACKEND,
        approved_sources=load_approved_sources_summary(),
        warnings=build_approval_warnings(request),
    )
