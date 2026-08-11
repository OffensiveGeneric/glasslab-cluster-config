"""FastAPI surface and deterministic workflow-family ranking.

POST /rank/workflow-family scores each candidate by query/summary token overlap
plus workflow-specific keyword hints and request-level metadata bonuses, then
returns the candidates sorted by descending score with a human-readable reason
per candidate. Ranking is fully deterministic: identical requests always rank
identically, with no model in the loop.
"""

from __future__ import annotations

import re
from collections import Counter

from fastapi import FastAPI

from .models import RankedCandidate, WorkflowFamilyRankRequest, WorkflowFamilyRankResponse

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Same shared lexicon the interpretation agent uses, so the ranker and the
# interpretation stage agree on what each workflow family means.
WORKFLOW_HINTS: dict[str, set[str]] = {
    'literature-to-experiment': {'paper', 'literature', 'claim', 'method', 'study', 'review'},
    'generic-tabular-benchmark': {'tabular', 'benchmark', 'dataset', 'csv', 'train', 'test', 'titanic'},
    'replication-lite': {'replicate', 'replication', 'reproduce', 'repeat', 'rerun'},
}


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(value.lower())


def score_candidate(query: str, workflow_id: str, summary: str, hints: dict[str, object]) -> tuple[float, str]:
    query_tokens = tokenize(query)
    summary_tokens = tokenize(summary)
    query_counts = Counter(query_tokens)
    summary_counts = Counter(summary_tokens)

    # Min-overlap counts each query token at most as often as it appears in the
    # summary, so a verbose summary cannot inflate a query word's contribution.
    overlap = sum(min(query_counts[token], summary_counts[token]) for token in query_counts)
    overlap_score = float(overlap)

    hint_score = 0.0
    matched_hints: list[str] = []
    # Keywords contribute +1 each, independent of the summary text: they reward
    # the query naming the family's own vocabulary.
    for token in WORKFLOW_HINTS.get(workflow_id, set()):
        if token in query_counts:
            hint_score += 1.0
            matched_hints.append(token)

    metadata_bonus = 0.0
    # Request-level hints are applied only to the family that can legitimately
    # use them (a declared dataset for tabular, a paper link for literature),
    # so generic metadata cannot inflate unrelated families.
    dataset_hint = hints.get('dataset_name')
    if workflow_id == 'generic-tabular-benchmark' and isinstance(dataset_hint, str) and dataset_hint.strip():
        metadata_bonus += 1.0
    source_type = hints.get('source_type')
    if workflow_id == 'literature-to-experiment' and source_type == 'paper-link':
        metadata_bonus += 1.0

    score = overlap_score + hint_score + metadata_bonus
    reasons: list[str] = []
    if overlap_score:
        reasons.append(f'query/summary token overlap={int(overlap_score)}')
    if matched_hints:
        reasons.append('matched workflow hints: ' + ', '.join(sorted(matched_hints)))
    if metadata_bonus:
        reasons.append(f'backend hints bonus={metadata_bonus:.1f}')
    if not reasons:
        reasons.append('no strong lexical match; kept as low-confidence fallback')
    return score, '; '.join(reasons)


def rank_workflow_families(request: WorkflowFamilyRankRequest) -> WorkflowFamilyRankResponse:
    ranked = []
    for candidate in request.candidates:
        score, reason = score_candidate(
            query=request.query,
            workflow_id=candidate.workflow_id,
            summary=candidate.summary,
            hints=request.hints,
        )
        ranked.append(RankedCandidate(workflow_id=candidate.workflow_id, score=score, reason=reason))
    # Descending score, then alphabetical id: a stable, fully deterministic
    # ordering so equal-scoring candidates never reorder across calls.
    ranked.sort(key=lambda item: (-item.score, item.workflow_id))
    return WorkflowFamilyRankResponse(
        request_id=request.request_id,
        ranked_candidates=ranked,
        ranking_basis='deterministic lexical overlap plus workflow-specific hint bonuses',
    )


app = FastAPI(title='glasslab-ranker', version='0.1.0')


@app.get('/healthz')
def healthz() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/rank/workflow-family', response_model=WorkflowFamilyRankResponse)
def rank_workflow_family(request: WorkflowFamilyRankRequest) -> WorkflowFamilyRankResponse:
    return rank_workflow_families(request)
