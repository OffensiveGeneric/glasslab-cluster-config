from __future__ import annotations

from pathlib import Path
from typing import Any

from .schemas import (
    ContextPacketRecord,
    KnowledgeEvent,
    SourceRecord,
    SourceType,
)


class KnowledgeManager:
    """Manages knowledge ingestion, indexing, and retrieval for the orchestrator."""

    def __init__(
        self,
        *,
        store: Any,
        root: Path,
    ) -> None:
        self.store = store
        self.root = root

    def ingest_source(
        self,
        *,
        source_type: SourceType,
        canonical_uri: str,
        run_scope: str | None = None,
        access_policy: str = 'run-private',
        source_version: str | None = None,
        content_digest: str,
        title: str,
        metadata: dict[str, Any] | None = None,
        parent_source_id: str | None = None,
        chunk_index: int | None = None,
        total_chunks: int | None = None,
    ) -> SourceRecord:
        """Ingest a source document or chunk."""
        from datetime import datetime

        record = SourceRecord(
            source_type=source_type,
            canonical_uri=canonical_uri,
            run_scope=run_scope,
            access_policy=access_policy,
            source_version=source_version,
            content_digest=content_digest,
            ingestion_timestamp=datetime.now(),
            title=title,
            metadata=metadata or {},
            parent_source_id=parent_source_id,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
        )
        self.store.ingest_source(record)
        self._emit_event(
            KnowledgeEvent.SOURCE_INGESTED,
            {
                'source_id': record.source_id,
                'source_type': source_type.value,
                'canonical_uri': canonical_uri,
                'run_scope': run_scope,
            },
        )
        return record

    def retrieve_context(
        self,
        *,
        run_id: str,
        agent: str,
        turn_number: int,
        turn_kind: str,
        query_or_retrieval_intent: str,
        index_version: str,
        source_ids_with_scores: list[dict[str, Any]],
        exact_text_supplied: str,
        token_budget: int,
    ) -> ContextPacketRecord:
        """Retrieve context and save the context packet."""
        used_tokens = len(exact_text_supplied) // 4
        record = ContextPacketRecord(
            run_id=run_id,
            agent=agent,
            turn_number=turn_number,
            turn_kind=turn_kind,
            query_or_retrieval_intent=query_or_retrieval_intent,
            index_version=index_version,
            source_ids_with_scores=source_ids_with_scores,
            exact_text_supplied=exact_text_supplied,
            token_budget=token_budget,
            used_tokens=used_tokens,
        )
        self.store.save_context_packet(record)
        self._emit_event(
            KnowledgeEvent.AGENT_CONTEXT_RETRIEVED,
            {
                'packet_id': record.packet_id,
                'run_id': run_id,
                'agent': agent,
                'turn_number': turn_number,
                'turn_kind': turn_kind,
            },
        )
        return record

    def retrieve(
        self,
        *,
        run_id: str,
        agent: str,
        turn_number: int,
        turn_kind: str,
        query: str,
        index_version: str = 'v1',
        max_results: int = 10,
        token_budget: int = 4000,
        run_scope: str | None = None,
        allowed_source_types: list[SourceType] | None = None,
    ) -> ContextPacketRecord:
        """Retrieve context for an agent turn and save the context packet."""
        source_ids_with_scores, exact_text_supplied = self.store.retrieve_context(
            run_id=run_id,
            agent=agent,
            turn_kind=turn_kind,
            query=query,
            index_version=index_version,
            max_results=max_results,
            token_budget=token_budget,
            run_scope=run_scope,
            source_types=allowed_source_types,
        )
        return self.retrieve_context(
            run_id=run_id,
            agent=agent,
            turn_number=turn_number,
            turn_kind=turn_kind,
            query_or_retrieval_intent=query,
            index_version=index_version,
            source_ids_with_scores=source_ids_with_scores,
            exact_text_supplied=exact_text_supplied,
            token_budget=token_budget,
        )

    def _emit_event(self, event_type: KnowledgeEvent, payload: dict[str, Any]) -> None:
        """Emit a knowledge event."""
        from .engine import ResearchOrchestrator

        # This will be called from the orchestrator context
        # In production, this would access the store through self.store
        pass
