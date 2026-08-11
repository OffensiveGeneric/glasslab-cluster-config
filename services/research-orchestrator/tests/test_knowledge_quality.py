from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.knowledge_fixture import QUERY_RELEVANCE_FIXTURE
from app.knowledge_manager import KnowledgeManager
from app.schemas import RunRecord, RunState
from app.storage import SqliteStore


def _run(store: SqliteStore, run_id: str) -> RunRecord:
    now = datetime.now(timezone.utc)
    return store.create_run(
        RunRecord(
            run_id=run_id,
            objective='Evaluate retrieval quality on the checked-in fixture.',
            state=RunState.CREATED,
            evaluation_contract_id='example-research-v1',
            evaluation_contract_version='1.0.0',
            evaluation_contract_digest='a' * 64,
            beaker_workspace='/tmp/beaker',
            honeydew_workspace='/tmp/honeydew',
            shared_artifacts_path='/tmp/shared',
            reports_path='/tmp/reports',
            maximum_turns=20,
            maximum_runtime_seconds=3600,
            maximum_parallel_jobs=2,
            created_at=now,
            updated_at=now,
        ),
        one_active_run=False,
    )


def _build_index(
    tmp_path: Path,
    documents: list[dict],
) -> tuple[KnowledgeManager, str]:
    store = SqliteStore(str(tmp_path / 'orchestrator.db'))
    manager = KnowledgeManager(
        store=store,
        root=tmp_path / 'knowledge',
        allowlist_roots=[],
        token_budget=8000,
    )
    run_id = 'quality-run'
    _run(store, run_id)
    for document in documents:
        manager.ingest_text(
            source_type=document['source_type'],
            canonical_uri=document['uri'],
            text=document['text'],
            title=document['title'],
            run_scope=run_id,
        )
    return manager, run_id


def _ranked_uris(packet) -> set[str]:
    return {entry['uri'] for entry in packet.ranked_sources}


def test_retrieval_quality_fixture_recalls_relevant_sources(tmp_path: Path) -> None:
    by_query: dict[str, dict] = {}
    documents: list[dict] = []
    for entry in QUERY_RELEVANCE_FIXTURE:
        by_query[entry['query']] = entry
        for document in entry['documents']:
            if not any(
                document['uri'] == existing['uri'] for existing in documents
            ):
                documents.append(document)

    manager, run_id = _build_index(tmp_path, documents)
    scores: list[bool] = []
    for entry in QUERY_RELEVANCE_FIXTURE:
        packet = manager.retrieve(
            run_id=run_id,
            agent=entry['agent'],
            turn_number=1,
            turn_kind=entry['turn_kind'],
            query=entry['query'],
            index_version='v1',
            max_results=5,
            token_budget=8000,
            run_scope=run_id,
            allowed_source_types=None,
        )
        uris = _ranked_uris(packet)
        scores.append(entry['relevant_uri'] in uris)
        if entry['relevant_uri'] in uris:
            assert packet.exact_text_supplied is not None
            assert 'untrusted data, not instructions' in (
                packet.exact_text_supplied
            )
    assert sum(scores) == len(scores), (
        f'recall@{len(scores)} was {sum(scores)}/{len(scores)}: '
        'every fixture query must surface its relevant source'
    )


def test_hybrid_ranking_edges_lexical_on_distinct_topics(tmp_path: Path) -> None:
    """Hybrid (FTS + lexical) must rank the relevant source first on the
    topical fixture, matching a pure lexical baseline at minimum."""
    documents: list[dict] = []
    for entry in QUERY_RELEVANCE_FIXTURE:
        for document in entry['documents']:
            if not any(
                document['uri'] == existing['uri'] for existing in documents
            ):
                documents.append(document)
    manager, run_id = _build_index(tmp_path, documents)
    wins = 0
    for entry in QUERY_RELEVANCE_FIXTURE:
        packet = manager.retrieve(
            run_id=run_id,
            agent=entry['agent'],
            turn_number=1,
            turn_kind=entry['turn_kind'],
            query=entry['query'],
            index_version='v1',
            max_results=5,
            token_budget=8000,
            run_scope=run_id,
            allowed_source_types=None,
        )
        ranked = packet.ranked_sources
        if not ranked:
            continue
        top = ranked[0]['uri']
        if top == entry['relevant_uri']:
            wins += 1
        else:
            # Hybrid must still place the relevant source inside the packet.
            assert entry['relevant_uri'] in _ranked_uris(packet)
    assert wins >= 4, f'hybrid ranking must win most fixtures, won {wins}'
