from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timezone
from typing import Any
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from xml.etree import ElementTree

from .config import Settings
from .schemas import ResearchProblemPaperCandidate


@dataclass(slots=True)
class ExternalLiteratureResult:
    selected_tracks: list[str]
    selected_queries: list[str]
    selected_papers: list[ResearchProblemPaperCandidate]
    coverage_summary: dict[str, Any]
    warnings: list[str]


GENERIC_QUERY_TERMS = {
    "with",
    "using",
    "compare",
    "comparison",
    "method",
    "methods",
    "methodology",
    "methodologies",
    "study",
    "studies",
    "open",
}


def build_external_literature_query(problem_statement: str, priorities: list[str]) -> str:
    parts = [problem_statement.strip()]
    parts.extend(priority.strip() for priority in priorities if priority.strip())
    return " ".join(parts).strip()


def _build_user_agent(settings: Settings) -> str:
    if settings.external_literature_mailto:
        return f"glasslab-workflow-api/0.1.0 (mailto:{settings.external_literature_mailto})"
    return "glasslab-workflow-api/0.1.0"


def _request_json(url: str, *, settings: Settings, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_obj = urllib_request.Request(
        url,
        headers={
            "User-Agent": _build_user_agent(settings),
            "Accept": "application/json",
            **(headers or {}),
        },
        method="GET",
    )
    with urllib_request.urlopen(request_obj, timeout=settings.external_literature_timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_text(url: str, *, settings: Settings, headers: dict[str, str] | None = None) -> str:
    request_obj = urllib_request.Request(
        url,
        headers={
            "User-Agent": _build_user_agent(settings),
            "Accept": "application/atom+xml,text/xml;q=0.9,*/*;q=0.8",
            **(headers or {}),
        },
        method="GET",
    )
    with urllib_request.urlopen(request_obj, timeout=settings.external_literature_timeout_seconds) as response:
        return response.read().decode("utf-8", errors="ignore")


def _normalize_terms(problem_statement: str, priorities: list[str]) -> list[str]:
    raw = " ".join([problem_statement, *priorities]).lower()
    tokens = []
    for token in raw.replace("/", " ").replace("-", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 4 and cleaned not in GENERIC_QUERY_TERMS:
            tokens.append(cleaned)
    return list(dict.fromkeys(tokens))


def _normalize_phrases(problem_statement: str, priorities: list[str]) -> list[str]:
    phrases: list[str] = []
    for phrase in priorities:
        normalized = _truncate(phrase, 120)
        if normalized and len(normalized.split()) >= 2:
            phrases.append(normalized.lower())
    return list(dict.fromkeys(phrases))


def _truncate(value: str | None, limit: int = 1200) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split()).strip()
    return normalized[:limit] or None


def _openalex_abstract(item: dict[str, Any]) -> str | None:
    inverted = item.get("abstract_inverted_index")
    if not isinstance(inverted, dict):
        return None
    words: dict[int, str] = {}
    for token, positions in inverted.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                words[position] = token
    if not words:
        return None
    return _truncate(" ".join(words[index] for index in sorted(words)))


def _candidate_provider(candidate: ResearchProblemPaperCandidate) -> str:
    for provider in candidate.tracks:
        if provider in {"openalex", "arxiv", "crossref", "dblp"}:
            return provider
    return "unknown"


def _title_tokens(title: str) -> set[str]:
    tokens: set[str] = set()
    for token in title.lower().replace("/", " ").replace("-", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 4:
            tokens.add(cleaned)
    return tokens


def _score_candidate(
    candidate: ResearchProblemPaperCandidate,
    terms: list[str],
    phrases: list[str] | None = None,
) -> ResearchProblemPaperCandidate:
    title_text = candidate.title.lower()
    tag_text = " ".join(candidate.tags).lower()
    abstract_text = (candidate.abstract_excerpt or "").lower()
    aux_text = " ".join(
        part
        for part in [
            candidate.why_seed,
            " ".join(candidate.tracks),
            " ".join(candidate.first_jobs),
            candidate.venue,
        ]
        if part
    ).lower()
    match_reasons: list[str] = []
    score = 0
    for phrase in phrases or []:
        if phrase in title_text:
            score += 6
            match_reasons.append(f"title matched phrase '{phrase}'")
        elif phrase in abstract_text:
            score += 4
            match_reasons.append(f"abstract matched phrase '{phrase}'")
        elif phrase in tag_text or phrase in aux_text:
            score += 2
            match_reasons.append(f"context matched phrase '{phrase}'")
    for term in terms:
        if term in title_text:
            score += 3
            match_reasons.append(f"title matched '{term}'")
        elif term in abstract_text:
            score += 2
            match_reasons.append(f"abstract matched '{term}'")
        elif term in tag_text:
            score += 2
            match_reasons.append(f"tags matched '{term}'")
        elif term in aux_text:
            score += 1
            match_reasons.append(f"context matched '{term}'")
    if candidate.pdf_url:
        score += 2
        match_reasons.append("direct PDF available")
    current_year = datetime.now(timezone.utc).year
    if candidate.year >= current_year - 2:
        score += 2
        match_reasons.append("recent paper")
    elif candidate.year >= current_year - 5:
        score += 1
        match_reasons.append("moderately recent paper")
    if candidate.priority == "P1":
        score += 1
        match_reasons.append("high priority candidate")
    return candidate.model_copy(update={"match_score": score, "match_reasons": match_reasons[:5]})


def _select_diverse_top_candidates(
    candidates: list[ResearchProblemPaperCandidate],
    max_candidate_papers: int,
) -> list[ResearchProblemPaperCandidate]:
    selected: list[ResearchProblemPaperCandidate] = []
    provider_counts: dict[str, int] = {}
    remaining = list(candidates)

    while remaining and len(selected) < max_candidate_papers:
        best_index = 0
        best_value: tuple[float, int, int] | None = None
        selected_title_tokens = [_title_tokens(candidate.title) for candidate in selected]

        for index, candidate in enumerate(remaining):
            provider = _candidate_provider(candidate)
            provider_penalty = provider_counts.get(provider, 0)
            title_tokens = _title_tokens(candidate.title)
            max_overlap = 0.0
            duplicate_like_penalty = 0.0
            for existing_tokens in selected_title_tokens:
                union = title_tokens | existing_tokens
                if not union:
                    continue
                overlap = len(title_tokens & existing_tokens) / len(union)
                max_overlap = max(max_overlap, overlap)
            if provider_penalty and max_overlap >= 0.45:
                duplicate_like_penalty = 4.0
            ranking_value = (
                float(candidate.match_score) - provider_penalty * 0.75 - max_overlap * 6.0 - duplicate_like_penalty,
                candidate.year,
                1 if candidate.pdf_url else 0,
            )
            if best_value is None or ranking_value > best_value:
                best_value = ranking_value
                best_index = index

        chosen = remaining.pop(best_index)
        selected.append(chosen)
        provider = _candidate_provider(chosen)
        provider_counts[provider] = provider_counts.get(provider, 0) + 1

    return selected


def _provider_tag(url: str | None, venue: str) -> list[str]:
    tags: list[str] = []
    if url and "arxiv.org" in url:
        tags.append("arxiv")
    if venue:
        tags.append(venue.lower().replace(" ", "_"))
    return list(dict.fromkeys(tags))


def _openalex_candidates(query: str, max_results: int, settings: Settings) -> list[ResearchProblemPaperCandidate]:
    params = urllib_parse.urlencode(
        {
            "search": query,
            "per-page": str(max_results),
            "filter": "is_retracted:false",
        }
    )
    payload = _request_json(f"{settings.external_literature_openalex_url}?{params}", settings=settings)
    results: list[ResearchProblemPaperCandidate] = []
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("display_name") or "").strip()
        if not title:
            continue
        year = int(item.get("publication_year") or 0) or 1900
        primary_location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
        source = primary_location.get("source") if isinstance(primary_location.get("source"), dict) else {}
        venue = str(source.get("display_name") or item.get("type") or "OpenAlex").strip()
        landing_page_url = primary_location.get("landing_page_url")
        pdf_url = primary_location.get("pdf_url")
        doi = str(item.get("doi") or "").strip()
        official_page = landing_page_url or doi or str(item.get("id") or "").strip() or None
        concepts = item.get("concepts") if isinstance(item.get("concepts"), list) else []
        tags = [
            str(concept.get("display_name") or "").strip().lower().replace(" ", "_")
            for concept in concepts[:5]
            if isinstance(concept, dict) and str(concept.get("display_name") or "").strip()
        ]
        authorship = item.get("authorships") if isinstance(item.get("authorships"), list) else []
        first_jobs: list[str] = []
        if authorship:
            first_jobs.append("review the abstract and compare methodology to the current session goal")
        candidate = ResearchProblemPaperCandidate(
            paper_id=str(item.get("id") or official_page or title).strip(),
            title=title,
            year=year,
            venue=venue,
            venue_id=str(source.get("id") or "").strip() or None,
            priority="P1",
            tracks=["external_literature", "openalex"],
            bounded_job_fit=3,
            replication_complexity=3,
            official_page=official_page,
            pdf_url=str(pdf_url).strip() or None,
            abstract_excerpt=_openalex_abstract(item),
            why_seed="Matched the external literature query through OpenAlex.",
            first_jobs=first_jobs,
            tags=list(dict.fromkeys(tags + _provider_tag(official_page, venue))),
        )
        results.append(candidate)
    return results


def _crossref_candidates(query: str, max_results: int, settings: Settings) -> list[ResearchProblemPaperCandidate]:
    params = urllib_parse.urlencode({"query.bibliographic": query, "rows": str(max_results)})
    payload = _request_json(f"{settings.external_literature_crossref_url}?{params}", settings=settings)
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    results: list[ResearchProblemPaperCandidate] = []
    for item in message.get("items", []):
        if not isinstance(item, dict):
            continue
        titles = item.get("title") if isinstance(item.get("title"), list) else []
        title = str(titles[0] if titles else "").strip()
        if not title:
            continue
        issued = item.get("issued") if isinstance(item.get("issued"), dict) else {}
        parts = issued.get("date-parts") if isinstance(issued.get("date-parts"), list) else []
        year = 1900
        if parts and isinstance(parts[0], list) and parts[0]:
            try:
                year = int(parts[0][0])
            except (TypeError, ValueError):
                year = 1900
        venue_values = item.get("container-title") if isinstance(item.get("container-title"), list) else []
        venue = str(venue_values[0] if venue_values else item.get("type") or "Crossref").strip()
        doi = str(item.get("DOI") or "").strip()
        official_page = f"https://doi.org/{doi}" if doi else None
        abstract_excerpt = _truncate(str(item.get("abstract") or "").replace("<jats:p>", " ").replace("</jats:p>", " "))
        link_items = item.get("link") if isinstance(item.get("link"), list) else []
        pdf_url = None
        for link in link_items:
            if not isinstance(link, dict):
                continue
            if str(link.get("content-type") or "").strip().lower() == "application/pdf":
                pdf_url = str(link.get("URL") or "").strip() or None
                if pdf_url:
                    break
        candidate = ResearchProblemPaperCandidate(
            paper_id=doi or official_page or title,
            title=title,
            year=year,
            venue=venue,
            venue_id=doi or None,
            priority="P2",
            tracks=["external_literature", "crossref"],
            bounded_job_fit=3,
            replication_complexity=3,
            official_page=official_page,
            pdf_url=pdf_url,
            abstract_excerpt=abstract_excerpt,
            why_seed="Matched the external literature query through Crossref metadata.",
            first_jobs=["review the abstract or landing page and compare to the session problem"],
            tags=_provider_tag(official_page, venue),
        )
        results.append(candidate)
    return results


def _arxiv_candidates(query: str, max_results: int, settings: Settings) -> list[ResearchProblemPaperCandidate]:
    params = urllib_parse.urlencode(
        {
            "search_query": f"all:{query}",
            "start": "0",
            "max_results": str(max_results),
        }
    )
    body = _request_text(f"{settings.external_literature_arxiv_url}?{params}", settings=settings)
    root = ElementTree.fromstring(body)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: list[ResearchProblemPaperCandidate] = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split()).strip()
        if not title:
            continue
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        try:
            year = int(published[:4])
        except ValueError:
            year = 1900
        official_page = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip() or None
        abstract_excerpt = _truncate(entry.findtext("atom:summary", default="", namespaces=ns) or "")
        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
                break
        candidate = ResearchProblemPaperCandidate(
            paper_id=official_page or title,
            title=title,
            year=year,
            venue="arXiv",
            venue_id=None,
            priority="P1",
            tracks=["external_literature", "arxiv"],
            bounded_job_fit=3,
            replication_complexity=3,
            official_page=official_page,
            pdf_url=pdf_url,
            abstract_excerpt=abstract_excerpt,
            why_seed="Matched the external literature query through arXiv search.",
            first_jobs=["review the abstract and identify a bounded baseline worth testing"],
            tags=["arxiv"],
        )
        results.append(candidate)
    return results


def _dblp_candidates(query: str, max_results: int, settings: Settings) -> list[ResearchProblemPaperCandidate]:
    params = urllib_parse.urlencode(
        {
            "q": query,
            "h": str(max_results),
            "format": "json",
        }
    )
    payload = _request_json(f"{settings.external_literature_dblp_url}?{params}", settings=settings)
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    hits = result.get("hits") if isinstance(result.get("hits"), dict) else {}
    hit_items = hits.get("hit")
    if isinstance(hit_items, dict):
        hit_iterable = [hit_items]
    elif isinstance(hit_items, list):
        hit_iterable = hit_items
    else:
        hit_iterable = []

    results: list[ResearchProblemPaperCandidate] = []
    for item in hit_iterable:
        if not isinstance(item, dict):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        title = str(info.get("title") or "").strip()
        if not title:
            continue
        try:
            year = int(str(info.get("year") or "1900"))
        except ValueError:
            year = 1900
        venue = str(info.get("venue") or info.get("type") or "DBLP").strip()
        venue_id = str(info.get("key") or "").strip() or None
        official_page = str(info.get("url") or "").strip() or None
        ee_value = info.get("ee")
        if isinstance(ee_value, list):
            ee_candidates = [str(entry).strip() for entry in ee_value if str(entry).strip()]
            ee_url = ee_candidates[0] if ee_candidates else None
        else:
            ee_url = str(ee_value or "").strip() or None
        pdf_url = ee_url if ee_url and ee_url.lower().endswith(".pdf") else None
        tags = _provider_tag(official_page or ee_url, venue)
        tags.append("dblp")
        candidate = ResearchProblemPaperCandidate(
            paper_id=venue_id or official_page or ee_url or title,
            title=title,
            year=year,
            venue=venue,
            venue_id=venue_id,
            priority="P2",
            tracks=["external_literature", "dblp"],
            bounded_job_fit=3,
            replication_complexity=3,
            official_page=official_page or ee_url,
            pdf_url=pdf_url,
            abstract_excerpt=None,
            why_seed="Matched the external literature query through DBLP metadata.",
            first_jobs=["review the landing page and determine whether it matches the current session problem"],
            tags=list(dict.fromkeys(tags)),
        )
        results.append(candidate)
    return results


def search_external_literature(
    *,
    problem_statement: str,
    priorities: list[str],
    max_candidate_papers: int,
    settings: Settings,
) -> ExternalLiteratureResult:
    query = build_external_literature_query(problem_statement, priorities)
    terms = _normalize_terms(problem_statement, priorities)
    phrases = _normalize_phrases(problem_statement, priorities)
    selected_tracks = ["external_literature"]
    selected_queries = [query]
    warnings: list[str] = []
    per_provider = max(max_candidate_papers, min(10, max_candidate_papers * 2))

    raw_candidates: list[ResearchProblemPaperCandidate] = []
    provider_counts: dict[str, int] = {}

    providers = [
        ("openalex", _openalex_candidates),
        ("arxiv", _arxiv_candidates),
        ("crossref", _crossref_candidates),
        ("dblp", _dblp_candidates),
    ]
    for provider_name, provider_fn in providers:
        try:
            provider_results = provider_fn(query, per_provider, settings)
            provider_counts[provider_name] = len(provider_results)
            raw_candidates.extend(provider_results)
            if provider_results:
                selected_tracks.append(provider_name)
        except Exception as exc:
            provider_counts[provider_name] = 0
            warnings.append(f"{provider_name} search failed: {exc}")

    deduped: dict[str, ResearchProblemPaperCandidate] = {}
    for candidate in raw_candidates:
        key = (
            (candidate.official_page or "").strip().lower()
            or (candidate.pdf_url or "").strip().lower()
            or candidate.title.strip().lower()
        )
        if not key or key in deduped:
            continue
        deduped[key] = _score_candidate(candidate, terms, phrases)

    ranked_candidates = sorted(
        deduped.values(),
        key=lambda item: (item.match_score, item.year, item.priority == "P1"),
        reverse=True,
    )
    selected_papers = _select_diverse_top_candidates(ranked_candidates, max_candidate_papers)

    coverage_summary = {
        "mode": "external_search",
        "query": query,
        "provider_counts": provider_counts,
        "selected_candidate_count": len(selected_papers),
        "ranking_mode": "heuristic-session-aware",
        "selected_provider_mix": sorted(
            {
                provider
                for candidate in selected_papers
                for provider in candidate.tracks
                if provider in {"openalex", "arxiv", "crossref", "dblp"}
            }
        ),
    }

    if not selected_papers and not warnings:
        warnings.append("external literature search returned no candidates")

    return ExternalLiteratureResult(
        selected_tracks=list(dict.fromkeys(selected_tracks)),
        selected_queries=selected_queries,
        selected_papers=selected_papers,
        coverage_summary=coverage_summary,
        warnings=warnings,
    )
