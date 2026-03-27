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
    HarvesterCoverageSummary,
    ModelBackendMetadata,
    NormalizeIntakeRequest,
    NormalizeIntakeResponse,
    NormalizedIntakeDraft,
    PaperHarvesterPlanRequest,
    PaperHarvesterPlanResponse,
    ProblemHarvesterPlanRequest,
    SeedPaperSummary,
    TrackDefinition,
    TrackQueryEntry,
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


def tokenize(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.lower()))


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


@lru_cache(maxsize=1)
def load_seed_manifest() -> dict:
    return yaml.safe_load(DEFAULT_SEED_MANIFEST.read_text())


def load_track_queries() -> list[TrackQueryEntry]:
    manifest = load_seed_manifest()
    entries: list[TrackQueryEntry] = []
    for item in manifest.get('track_queries', []):
        track = str(item.get('track', '')).strip()
        queries = [str(query).strip() for query in item.get('queries', []) if str(query).strip()]
        if not track:
            continue
        entries.append(TrackQueryEntry(track=track, queries=queries))
    return entries


def load_tracks() -> list[TrackDefinition]:
    query_map = {entry.track: entry.queries for entry in load_track_queries()}
    manifest = load_seed_manifest()
    tracks: list[TrackDefinition] = []
    for item in manifest.get('tracks', []):
        track_id = str(item.get('id', '')).strip()
        if not track_id:
            continue
        tracks.append(
            TrackDefinition(
                track_id=track_id,
                description=str(item.get('description', '')).strip(),
                default_priority=str(item.get('default_priority', 'P2')).strip() or 'P2',
                queries=query_map.get(track_id, []),
            )
        )
    return tracks


def load_seed_papers() -> list[SeedPaperSummary]:
    manifest = load_seed_manifest()
    papers: list[SeedPaperSummary] = []
    for item in manifest.get('papers', []):
        paper_id = str(item.get('id', '')).strip()
        title = str(item.get('title', '')).strip()
        venue_id = str(item.get('venue_id', '')).strip()
        venue = str(item.get('venue', '')).strip()
        if not all((paper_id, title, venue_id, venue)):
            continue
        papers.append(
            SeedPaperSummary(
                paper_id=paper_id,
                title=title,
                year=int(item.get('year', 0)),
                venue=venue,
                venue_id=venue_id,
                priority=str(item.get('priority', 'P2')).strip() or 'P2',
                tracks=[str(track).strip() for track in item.get('tracks', []) if str(track).strip()],
                bounded_job_fit=int(item.get('bounded_job_fit', 0)),
                replication_complexity=int(item.get('replication_complexity', 0)),
                official_page=str(item.get('official_page', '')).strip() or None,
                pdf_url=str(item.get('pdf_url', '')).strip() or None,
                why_seed=str(item.get('why_seed', '')).strip(),
                first_jobs=[str(job).strip() for job in item.get('first_jobs', []) if str(job).strip()],
                tags=[str(tag).strip() for tag in item.get('tags', []) if str(tag).strip()],
            )
        )
    return papers


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


def filter_seed_papers(track_ids: list[str], priorities: list[str], max_papers: int) -> list[SeedPaperSummary]:
    papers = load_seed_papers()
    if track_ids:
        track_set = set(track_ids)
        papers = [paper for paper in papers if track_set.intersection(paper.tracks)]
    if priorities:
        priority_set = set(priorities)
        papers = [paper for paper in papers if paper.priority in priority_set]
    papers.sort(key=lambda paper: (-paper.bounded_job_fit, paper.replication_complexity, paper.paper_id))
    return papers[:max_papers]


def score_track_for_problem(track: TrackDefinition, problem_tokens: set[str]) -> int:
    corpus = " ".join([track.track_id, track.description, *track.queries])
    overlap = tokenize(corpus).intersection(problem_tokens)
    return len(overlap)


def score_paper_for_problem(paper: SeedPaperSummary, problem_tokens: set[str]) -> tuple[int, int, int]:
    corpus = " ".join(
        [
            paper.title,
            paper.why_seed,
            *paper.tags,
            *paper.tracks,
            *paper.first_jobs,
        ]
    )
    overlap = tokenize(corpus).intersection(problem_tokens)
    return (len(overlap), paper.bounded_job_fit, -paper.replication_complexity)


def build_paper_match_reasons(paper: SeedPaperSummary, problem_tokens: set[str]) -> list[str]:
    reasons: list[str] = []
    title_overlap = sorted(tokenize(paper.title).intersection(problem_tokens))
    tag_overlap = sorted({token.lower() for token in paper.tags}.intersection(problem_tokens))
    track_overlap = sorted(tokenize(" ".join(paper.tracks)).intersection(problem_tokens))
    if title_overlap:
        reasons.append('title overlap: ' + ', '.join(title_overlap[:4]))
    if tag_overlap:
        reasons.append('tag overlap: ' + ', '.join(tag_overlap[:4]))
    if track_overlap:
        reasons.append('track overlap: ' + ', '.join(track_overlap[:4]))
    if paper.bounded_job_fit >= 4:
        reasons.append(f'bounded job fit is strong ({paper.bounded_job_fit}/5)')
    if not reasons:
        reasons.append('selected from approved fallback seed corpus')
    return reasons


def build_coverage_summary(
    problem_statement: str,
    scored_tracks: list[tuple[int, TrackDefinition]],
    selected_tracks: list[TrackDefinition],
    selected_papers: list[SeedPaperSummary],
    *,
    fallback_track_ids: list[str] | None = None,
) -> HarvesterCoverageSummary:
    problem_tokens = tokenize(problem_statement)
    score_map = {track.track_id: score for score, track in scored_tracks}
    selected_track_scores = {
        track.track_id: score_map.get(track.track_id, 0)
        for track in selected_tracks
    }
    selected_paper_scores = {
        paper.paper_id: score_paper_for_problem(paper, problem_tokens)[0]
        for paper in selected_papers
    }
    matched_track_ids = [track.track_id for score, track in scored_tracks if score > 0]
    fallback_track_ids = fallback_track_ids or []
    notes: list[str] = []
    coverage_mode = 'strong'

    best_track_score = max(score_map.values(), default=0)
    best_paper_score = max(selected_paper_scores.values(), default=0)

    if not matched_track_ids:
        coverage_mode = 'fallback'
        notes.append('no track-level match; plan was built from the approved seed corpus fallback')
    elif best_track_score <= 1 or best_paper_score <= 1:
        coverage_mode = 'thin'
        notes.append('problem only weakly overlaps the approved seed manifest')

    if selected_papers and best_paper_score == 0:
        notes.append('selected papers have no lexical overlap with the problem statement; treat this as a coarse seed shortlist')
    if not selected_papers:
        notes.append('no approved seed papers matched strongly enough')

    return HarvesterCoverageSummary(
        coverage_mode=coverage_mode,
        problem_token_count=len(problem_tokens),
        matched_track_ids=matched_track_ids,
        fallback_track_ids=fallback_track_ids,
        selected_track_scores=selected_track_scores,
        selected_paper_scores=selected_paper_scores,
        notes=notes,
    )


def build_problem_harvester_plan(request: ProblemHarvesterPlanRequest) -> PaperHarvesterPlanResponse:
    problem_tokens = tokenize(request.problem_statement)
    tracks = load_tracks()
    scored_tracks = [
        (score_track_for_problem(track, problem_tokens), track)
        for track in tracks
    ]
    selected_tracks = [track for score, track in scored_tracks if score > 0]
    fallback_track_ids: list[str] = []
    if not selected_tracks:
        selected_tracks = [track for track in tracks if track.track_id in {'literature_screening', 'benchmarks_reproducibility'}]
        fallback_track_ids = [track.track_id for track in selected_tracks]
    selected_track_ids = [track.track_id for track in selected_tracks]
    selected_queries = [
        TrackQueryEntry(track=track.track_id, queries=track.queries)
        for track in selected_tracks
        if track.queries
    ]

    candidate_papers = filter_seed_papers(selected_track_ids, request.priorities, max(10, request.max_papers))
    candidate_papers.sort(
        key=lambda paper: score_paper_for_problem(paper, problem_tokens),
        reverse=True,
    )
    selected_papers = [
        paper.model_copy(
            update={
                'match_score': score_paper_for_problem(paper, problem_tokens)[0],
                'match_reasons': build_paper_match_reasons(paper, problem_tokens),
            }
        )
        for paper in candidate_papers[:request.max_papers]
    ]

    warnings: list[str] = []
    coverage_summary = build_coverage_summary(
        request.problem_statement,
        scored_tracks,
        selected_tracks,
        selected_papers,
        fallback_track_ids=fallback_track_ids,
    )
    if coverage_summary.coverage_mode == 'fallback':
        warnings.append('no track-level seed match; literature harvest is using the approved corpus fallback')
    elif coverage_summary.coverage_mode == 'thin':
        warnings.append('problem only weakly overlaps the approved seed manifest; selected papers may be coarse matches')
    if not selected_papers:
        warnings.append('no approved seed papers matched the research problem strongly enough')

    return PaperHarvesterPlanResponse(
        request_id=request.request_id,
        selected_tracks=selected_tracks,
        selected_queries=selected_queries,
        selected_papers=selected_papers,
        approved_sources=load_approved_sources_summary(),
        coverage_summary=coverage_summary,
        warnings=warnings,
    )


def build_harvester_plan(request: PaperHarvesterPlanRequest) -> PaperHarvesterPlanResponse:
    tracks = load_tracks()
    track_map = {track.track_id: track for track in tracks}
    selected_track_ids = request.track_ids or [track.track_id for track in tracks]
    selected_tracks = [track_map[track_id] for track_id in selected_track_ids if track_id in track_map]
    selected_queries = [
        TrackQueryEntry(track=track.track_id, queries=track.queries)
        for track in selected_tracks
        if track.queries
    ]
    selected_papers = filter_seed_papers(selected_track_ids, request.priorities, request.max_papers)

    warnings: list[str] = []
    unknown_tracks = [track_id for track_id in selected_track_ids if track_id not in track_map]
    if unknown_tracks:
        warnings.append('unknown track ids ignored: ' + ', '.join(unknown_tracks))
    if not selected_papers:
        warnings.append('no seed papers matched the requested track/priority filters')

    coverage_summary = HarvesterCoverageSummary(
        coverage_mode='filtered',
        problem_token_count=0,
        matched_track_ids=selected_track_ids,
        fallback_track_ids=[],
        selected_track_scores={track.track_id: 0 for track in selected_tracks},
        selected_paper_scores={paper.paper_id: paper.bounded_job_fit for paper in selected_papers},
        notes=['track/priority filter applied against the approved seed corpus'],
    )

    return PaperHarvesterPlanResponse(
        request_id=request.request_id,
        selected_tracks=selected_tracks,
        selected_queries=selected_queries,
        selected_papers=selected_papers,
        approved_sources=load_approved_sources_summary(),
        coverage_summary=coverage_summary,
        warnings=warnings,
    )


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


@app.get('/paper-harvester/tracks', response_model=list[TrackDefinition])
def paper_harvester_tracks() -> list[TrackDefinition]:
    return load_tracks()


@app.get('/paper-harvester/papers', response_model=list[SeedPaperSummary])
def paper_harvester_papers(track: str | None = None, priority: str | None = None) -> list[SeedPaperSummary]:
    track_ids = [track.strip()] if isinstance(track, str) and track.strip() else []
    priorities = [priority.strip()] if isinstance(priority, str) and priority.strip() else []
    return filter_seed_papers(track_ids, priorities, max_papers=50)


@app.post('/paper-harvester/plan', response_model=PaperHarvesterPlanResponse)
def paper_harvester_plan(request: PaperHarvesterPlanRequest) -> PaperHarvesterPlanResponse:
    return build_harvester_plan(request)


@app.post('/paper-harvester/plan-from-problem', response_model=PaperHarvesterPlanResponse)
def paper_harvester_plan_from_problem(request: ProblemHarvesterPlanRequest) -> PaperHarvesterPlanResponse:
    return build_problem_harvester_plan(request)


@app.post('/normalize-intake', response_model=NormalizeIntakeResponse)
def normalize_intake(request: NormalizeIntakeRequest) -> NormalizeIntakeResponse:
    return NormalizeIntakeResponse(
        request_id=request.request_id,
        draft=build_normalized_draft(request),
        model_backend=MODEL_BACKEND,
        approved_sources=load_approved_sources_summary(),
        warnings=build_approval_warnings(request),
    )
