#!/usr/bin/env python3
"""One-time, fail-closed import of an orchestrator SQLite database to Postgres."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from app.postgres_store import PostgresStore
from psycopg.types.json import Jsonb


TABLES = (
    ('runs', 'orchestrator_runs', ('run_id', 'state', 'version', 'payload', 'created_at', 'updated_at')),
    ('turns', 'orchestrator_turns', ('turn_id', 'run_id', 'status', 'payload', 'created_at', 'updated_at')),
    ('actions', 'orchestrator_actions', ('action_id', 'run_id', 'approval_status', 'idempotency_key', 'payload', 'created_at', 'updated_at')),
    ('jobs', 'orchestrator_jobs', ('job_id', 'run_id', 'action_id', 'status', 'idempotency_key', 'payload', 'created_at', 'updated_at')),
    ('artifacts', 'orchestrator_artifacts', ('artifact_id', 'run_id', 'job_id', 'payload', 'created_at')),
    ('datasets', 'orchestrator_datasets', ('dataset_id', 'payload', 'created_at')),
    ('events', 'orchestrator_events', ('event_id', 'run_id', 'sequence_number', 'source', 'event_type', 'payload', 'timestamp')),
    ('knowledge_sources', 'orchestrator_knowledge_sources', ('source_id', 'source_type', 'canonical_uri', 'run_scope', 'digest', 'payload', 'ingested_at')),
    ('knowledge_chunks', 'orchestrator_knowledge_chunks', ('chunk_id', 'source_id', 'chunk_index', 'text', 'payload')),
    ('context_packets', 'orchestrator_context_packets', ('packet_id', 'run_id', 'payload', 'created_at')),
)


def payload_for(source_table: str, row: sqlite3.Row) -> dict:
    """Normalize the three SQLite tables that did not use a payload column."""
    if source_table == 'knowledge_sources':
        return {
            'source_id': row['source_id'], 'source_type': row['source_type'],
            'canonical_uri': row['canonical_uri'], 'run_scope': row['run_scope'],
            'access_policy': row['access_policy'], 'source_version': row['source_version'],
            'digest': row['digest'], 'ingested_at': row['ingested_at'],
            'index_version': row['index_version'], 'title': row['title'],
            'metadata': json.loads(row['metadata']), 'parent_source_id': row['parent_source_id'],
        }
    if source_table == 'knowledge_chunks':
        return {
            'chunk_id': row['chunk_id'], 'source_id': row['source_id'],
            'chunk_index': row['chunk_index'], 'text': row['text'],
            'digest': row['digest'], 'token_count': row['token_count'],
            'index_version': row['index_version'],
        }
    if source_table == 'context_packets':
        return {
            'packet_id': row['packet_id'], 'run_id': row['run_id'],
            'agent': row['agent'], 'turn_number': row['turn_number'],
            'turn_kind': row['turn_kind'], 'query': row['query'],
            'index_version': row['index_version'],
            'ranked_sources': json.loads(row['ranked_sources']),
            'exact_text_supplied': row['exact_text_supplied'],
            'token_budget': row['token_budget'], 'created_at': row['created_at'],
        }
    return json.loads(row['payload'])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite-path', required=True)
    parser.add_argument('--postgres-dsn', required=True)
    parser.add_argument('--apply', action='store_true', help='perform the import')
    args = parser.parse_args()

    source_path = Path(args.sqlite_path)
    if not source_path.is_file():
        parser.error(f'SQLite database does not exist: {source_path}')
    if not args.apply:
        print('dry run: pass --apply to import; no database was changed')
        return 0

    destination = PostgresStore(args.postgres_dsn)
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        with destination.transaction() as conn:
            existing = conn.execute('SELECT COUNT(*) AS count FROM orchestrator_runs').fetchone()['count']
            if existing:
                raise RuntimeError('destination is not empty; refusing to merge an ambiguous SQLite import')
            for source_table, destination_table, columns in TABLES:
                exists = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (source_table,)).fetchone()
                if not exists:
                    continue
                rows = source.execute(f"SELECT {', '.join(columns)} FROM {source_table}").fetchall()
                if not rows:
                    continue
                placeholders = ', '.join(['%s'] * len(columns))
                statement = f"INSERT INTO {destination_table} ({', '.join(columns)}) VALUES ({placeholders})"
                for row in rows:
                    values = [
                        Jsonb(payload_for(source_table, row)) if column == 'payload' else row[column]
                        for column in columns
                    ]
                    conn.execute(statement, values)
                print(f'imported {len(rows)} {source_table} rows')
    finally:
        source.close()
    print('SQLite import completed. Keep the source file until live readiness and recovery checks pass.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'import failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
