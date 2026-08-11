#!/usr/bin/env python3
"""One-shot migration from the JSON file store into Postgres.

Idempotent: the INSERT uses ON CONFLICT DO UPDATE on the fixed store_key
``'default'``, so re-running safely replaces the single authoritative row
without creating duplicates or leaving stale state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser(description='Import workflow-api JSON state into the Postgres workflow_state table.')
    parser.add_argument('--json-path', required=True, help='Path to run-store.json')
    parser.add_argument('--dsn', required=True, help='Postgres connection string')
    args = parser.parse_args()

    json_path = Path(args.json_path)
    payload = json.loads(json_path.read_text(encoding='utf-8'))

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS workflow_state (
                    store_key TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                '''
            )
            # The entire JSON file becomes a single row keyed by 'default'.
            # ON CONFLICT DO UPDATE makes the migration idempotent: re-running
            # replaces the row instead of duplicating it.
            cur.execute(
                '''
                INSERT INTO workflow_state (store_key, payload, updated_at)
                VALUES (%s, %s::jsonb, NOW())
                ON CONFLICT (store_key) DO UPDATE
                SET payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                ''',
                ('default', json.dumps(payload)),
            )
        conn.commit()

    print(f'Imported {json_path} into workflow_state(default).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
