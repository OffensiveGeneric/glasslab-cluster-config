from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import EventRecord


@dataclass
class RetrievalPacket:
    exact_text_supplied: str | None
    sources: list[dict[str, Any]]
    token_count: int


class KnowledgeManager:
    def __init__(
        self,
        *,
        store: Any,
        root: Path,
    ) -> None:
        self.store = store
        self.root = root

    def retrieve(
        self,
        *,
        run_id: str,
        agent: str,
        turn_number: int,
        turn_kind: str,
        query: str,
        index_version: str,
        max_results: int,
        token_budget: int,
        run_scope: str,
        allowed_source_types: list[str] | None,
    ) -> RetrievalPacket:
        events = self.store.list_events(run_id)
        filtered_events = [
            e for e in events if self._enforce_access_control(e, run_id, agent)
        ]
        filtered_events = [
            e for e in filtered_events if self._exclude_secrets(e)
        ]
        results = []
        for event in filtered_events:
            if event.event_type in (
                'artifact.recorded',
                'agent.output_repaired',
                'agent.file_repair_completed',
            ):
                artifact_uri = self._extract_artifact_uri(event)
                if artifact_uri:
                    results.append({
                        'event': event,
                        'artifact_uri': artifact_uri,
                    })
        if allowed_source_types:
            results = [
                r for r in results
                if any(t in r['artifact_uri'] for t in allowed_source_types)
            ]
        scored = self._lexical_vector_hybrid_rank(query, results, max_results)
        tokenized = self._enforce_token_budget(scored, token_budget)
        exact_text = self._build_context_string(tokenized)
        sources = [
            {
                'event_id': r['event'].event_id,
                'event_type': r['event'].event_type,
                'artifact_uri': r['artifact_uri'],
                'score': r.get('score', 0),
            }
            for r in tokenized
        ]
        return RetrievalPacket(
            exact_text_supplied=exact_text,
            sources=sources,
            token_count=sum(r.get('token_count', 0) for r in tokenized),
        )

    def _enforce_access_control(
        self,
        event: EventRecord,
        run_id: str,
        agent: str,
    ) -> bool:
        if event.event_type in (
            'agent.turn_started',
            'agent.turn_completed',
            'action.proposed',
            'artifact.recorded',
            'agent.output_repaired',
            'agent.file_repair_completed',
            'agent.session_rotated',
        ):
            return True
        return False

    def _exclude_secrets(self, event: EventRecord) -> bool:
        secret_patterns = [
            r'password',
            r'api[_-]?key',
            r'secret',
            r'token',
            r'credential',
            r'private[_-]?key',
            r'auth[_-]?header',
        ]
        payload_str = str(event.payload)
        for pattern in secret_patterns:
            if re.search(pattern, payload_str, re.IGNORECASE):
                return False
        return True

    def _extract_artifact_uri(self, event: EventRecord) -> str | None:
        if event.event_type == 'artifact.recorded':
            artifact = event.payload.get('artifact', {})
            if artifact and 'uri' in artifact:
                return artifact['uri']
            if 'uri' in event.payload:
                return event.payload['uri']
        elif event.event_type in (
            'agent.output_repaired',
            'agent.file_repair_completed',
        ):
            if 'repair' in event.payload and 'path' in event.payload:
                return f"artifact://{event.run_id}/workspace/{event.payload['path']}"
        return None

    def _lexical_vector_hybrid_rank(
        self,
        query: str,
        results: list[dict[str, Any]],
        max_results: int,
    ) -> list[dict[str, Any]]:
        query_terms = set(query.lower().split())
        for result in results:
            event = result['event']
            score = 0
            payload_str = str(event.payload).lower()
            for term in query_terms:
                if term in payload_str:
                    score += 1
            if event.event_type == 'artifact.recorded':
                score += 2
            artifact_uri = result.get('artifact_uri', '')
            if artifact_uri:
                score += 1
            result['score'] = score
        sorted_results = sorted(
            results, key=lambda x: x['score'], reverse=True
        )
        return sorted_results[:max_results]

    def _enforce_token_budget(
        self,
        results: list[dict[str, Any]],
        token_budget: int,
    ) -> list[dict[str, Any]]:
        total_tokens = 0
        tokenized = []
        for result in results:
            event = result['event']
            content = str(event.payload)[:1000]
            tokens = len(content.split())
            result['token_count'] = tokens
            if total_tokens + tokens <= token_budget:
                total_tokens += tokens
                tokenized.append(result)
        return tokenized

    def _build_context_string(
        self,
        results: list[dict[str, Any]],
    ) -> str | None:
        if not results:
            return None
        sections = []
        for result in results:
            event = result['event']
            artifact_uri = result.get('artifact_uri', 'unknown')
            section = (
                f"[Event {event.event_id}] {event.event_type}\n"
                f"Artifact: {artifact_uri}\n"
                f"Payload: {event.payload}"
            )
            sections.append(section)
        return '\n\n'.join(sections)
