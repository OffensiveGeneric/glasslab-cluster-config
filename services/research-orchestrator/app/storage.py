from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Iterator

from .schemas import (
    ActionRecord,
    AgentName,
    ApprovalStatus,
    ArtifactRecord,
    ContextPacket,
    EventRecord,
    IngestedDatasetRecord,
    JobRecord,
    JobStatus,
    KnowledgeChunk,
    KnowledgeSource,
    RunRecord,
    RunState,
    SourceType,
    TERMINAL_STATES,
    TurnKind,
    TurnRecord,
    utc_now,
)
from .state_machine import HUMAN_WAIT_STATES, validate_transition


class RecordNotFound(KeyError):
    pass


class ConcurrencyConflict(RuntimeError):
    pass


def _dump(record: Any) -> str:
    return record.model_dump_json()


class SqliteStore:
    """Single-replica durable store with transactional state and event writes."""

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self._lock = RLock()
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=30000')
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute('BEGIN IMMEDIATE')
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_state_idx ON runs(state);

                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS turns_run_idx ON turns(run_id, created_at);

                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    approval_status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS actions_run_idx ON actions(run_id, created_at);

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    action_id TEXT NOT NULL REFERENCES actions(action_id),
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_run_idx ON jobs(run_id, created_at);

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    job_id TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifacts_run_idx
                ON artifacts(run_id, created_at);

                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS datasets_created_idx
                ON datasets(created_at);

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    sequence_number INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    UNIQUE(run_id, sequence_number)
                );
                CREATE INDEX IF NOT EXISTS events_run_idx
                ON events(run_id, sequence_number);

                -- Knowledge store tables. The orchestrator has no formal
                -- migration framework; schema drift is handled by additive
                -- CREATE TABLE IF NOT EXISTS statements that run on every
                -- startup, so a new deployment upgrades an existing SQLite
                -- file by creating the new tables and leaving old rows intact.
                -- knowledge_sources is content-addressed: digest is the
                -- natural key for dedup, and source_id remains the stable
                -- surrogate used by the FTS chunk rows.
                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    canonical_uri TEXT NOT NULL,
                    run_scope TEXT,
                    access_policy TEXT NOT NULL,
                    source_version TEXT,
                    digest TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    index_version TEXT NOT NULL,
                    title TEXT,
                    metadata TEXT NOT NULL,
                    parent_source_id TEXT
                );
                CREATE INDEX IF NOT EXISTS knowledge_sources_type_idx
                ON knowledge_sources(source_type);
                CREATE INDEX IF NOT EXISTS knowledge_sources_scope_idx
                ON knowledge_sources(run_scope);
                CREATE INDEX IF NOT EXISTS knowledge_sources_digest_idx
                ON knowledge_sources(digest);
                -- Dedup guard: identical content re-ingested from the same
                -- canonical URI must resolve to one source row so the
                -- knowledge:// URI stays stable. Distinct URIs with equal
                -- content are deliberately allowed (provenance preserved).
                CREATE UNIQUE INDEX IF NOT EXISTS
                knowledge_sources_digest_uri_uniq
                ON knowledge_sources(digest, canonical_uri);

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL
                        REFERENCES knowledge_sources(source_id)
                        ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    index_version TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS knowledge_chunks_source_idx
                ON knowledge_chunks(source_id);

                -- FTS5 is the lexical half of hybrid retrieval. chunk_id is
                -- the rowid-style key linking to knowledge_chunks; the rank is
                -- read back to feed the combined lexical/BM25 score in the
                -- knowledge manager.
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
                USING fts5(chunk_id, text);

                CREATE TABLE IF NOT EXISTS context_packets (
                    packet_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    agent TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    turn_kind TEXT NOT NULL,
                    query TEXT NOT NULL,
                    index_version TEXT NOT NULL,
                    ranked_sources TEXT NOT NULL,
                    exact_text_supplied TEXT,
                    token_budget INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                -- Per-turn context packets are durable so a report can cite
                -- exactly which retrieval grounded a claim (knowledge://context
                -- URIs) even long after the turn finished.
                CREATE INDEX IF NOT EXISTS context_packets_run_idx
                ON context_packets(run_id, created_at);
                '''
            )

    def ping(self) -> bool:
        with self._connect() as connection:
            return connection.execute('SELECT 1').fetchone()[0] == 1

    def _append_event_conn(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        source: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> EventRecord:
        row = connection.execute(
            '''
            SELECT COALESCE(MAX(sequence_number), 0) + 1
            FROM events WHERE run_id = ?
            ''',
            (run_id,),
        ).fetchone()
        event = EventRecord(
            sequence_number=int(row[0]),
            run_id=run_id,
            source=source,
            event_type=event_type,
            payload=payload,
        )
        connection.execute(
            '''
            INSERT INTO events (
                event_id, run_id, sequence_number, source, event_type,
                payload, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                event.event_id,
                event.run_id,
                event.sequence_number,
                event.source,
                event.event_type,
                _dump(event),
                event.timestamp.isoformat(),
            ),
        )
        return event

    def append_event(
        self,
        *,
        run_id: str,
        source: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> EventRecord:
        with self.transaction() as connection:
            return self._append_event_conn(
                connection,
                run_id=run_id,
                source=source,
                event_type=event_type,
                payload=payload or {},
            )

    def create_run(self, record: RunRecord, *, one_active_run: bool) -> RunRecord:
        terminal = tuple(state.value for state in TERMINAL_STATES)
        placeholders = ','.join('?' for _ in terminal)
        with self.transaction() as connection:
            if one_active_run:
                active = connection.execute(
                    f'SELECT run_id FROM runs WHERE state NOT IN ({placeholders}) LIMIT 1',
                    terminal,
                ).fetchone()
                if active is not None:
                    raise ConcurrencyConflict(
                        f'active run already exists: {active["run_id"]}'
                    )
            connection.execute(
                '''
                INSERT INTO runs (
                    run_id, state, version, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.run_id,
                    record.state.value,
                    record.version,
                    _dump(record),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
            self._append_event_conn(
                connection,
                run_id=record.run_id,
                source='orchestrator',
                event_type='run.created',
                payload={'objective': record.objective, 'state': record.state.value},
            )
        return record

    def get_run(self, run_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload FROM runs WHERE run_id = ?',
                (run_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(run_id)
        return RunRecord.model_validate_json(row['payload'])

    def list_runs(self) -> list[RunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT payload FROM runs ORDER BY created_at DESC'
            ).fetchall()
        return [RunRecord.model_validate_json(row['payload']) for row in rows]

    def list_active_runs(self) -> list[RunRecord]:
        terminal = tuple(state.value for state in TERMINAL_STATES)
        placeholders = ','.join('?' for _ in terminal)
        with self._connect() as connection:
            rows = connection.execute(
                f'''
                SELECT payload FROM runs
                WHERE state NOT IN ({placeholders})
                ORDER BY created_at
                ''',
                terminal,
            ).fetchall()
        return [RunRecord.model_validate_json(row['payload']) for row in rows]

    def replace_run(self, record: RunRecord, *, expected_version: int) -> RunRecord:
        now = utc_now()
        updated = record.model_copy(
            update={'version': expected_version + 1, 'updated_at': now}
        )
        with self.transaction() as connection:
            cursor = connection.execute(
                '''
                UPDATE runs
                SET state = ?, version = ?, payload = ?, updated_at = ?
                WHERE run_id = ? AND version = ?
                ''',
                (
                    updated.state.value,
                    updated.version,
                    _dump(updated),
                    updated.updated_at.isoformat(),
                    updated.run_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyConflict(
                    f'run was updated concurrently: {record.run_id}'
                )
        return updated

    def reset_methodology_revision_budget(
        self,
        run_id: str,
        *,
        reason: str,
    ) -> RunRecord:
        with self.transaction() as connection:
            row = connection.execute(
                'SELECT payload, version FROM runs WHERE run_id = ?',
                (run_id,),
            ).fetchone()
            if row is None:
                raise RecordNotFound(run_id)
            current = RunRecord.model_validate_json(row['payload'])
            now = utc_now()
            updated = current.model_copy(
                update={
                    'methodology_revision_count': 0,
                    'version': int(row['version']) + 1,
                    'updated_at': now,
                }
            )
            cursor = connection.execute(
                '''
                UPDATE runs
                SET state = ?, version = ?, payload = ?, updated_at = ?
                WHERE run_id = ? AND version = ?
                ''',
                (
                    updated.state.value,
                    updated.version,
                    _dump(updated),
                    updated.updated_at.isoformat(),
                    run_id,
                    int(row['version']),
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyConflict(
                    f'run was updated concurrently: {run_id}'
                )
            self._append_event_conn(
                connection,
                run_id=run_id,
                source='orchestrator',
                event_type='methodology.revision_budget_reset',
                payload={
                    'previous_revision_count': (
                        current.methodology_revision_count
                    ),
                    'revision_count': 0,
                    'reason': reason,
                },
            )
        return updated

    def transition_run(
        self,
        run_id: str,
        target: RunState,
        *,
        source: str = 'orchestrator',
        payload: dict[str, Any] | None = None,
        updates: dict[str, Any] | None = None,
    ) -> RunRecord:
        with self.transaction() as connection:
            row = connection.execute(
                'SELECT payload, version FROM runs WHERE run_id = ?',
                (run_id,),
            ).fetchone()
            if row is None:
                raise RecordNotFound(run_id)
            current = RunRecord.model_validate_json(row['payload'])
            validate_transition(current.state, target)
            now = utc_now()
            runtime_updates: dict[str, Any] = {}
            if (
                target in HUMAN_WAIT_STATES
                and current.state not in HUMAN_WAIT_STATES
            ):
                active_runtime = current.active_runtime_seconds
                if current.active_since is not None:
                    active_runtime += max(
                        0.0,
                        (now - current.active_since).total_seconds(),
                    )
                runtime_updates = {
                    'active_runtime_seconds': active_runtime,
                    'active_since': None,
                }
            elif (
                current.state in HUMAN_WAIT_STATES
                and target not in HUMAN_WAIT_STATES
                and target not in TERMINAL_STATES
                and target != RunState.PAUSED
            ):
                runtime_updates = {'active_since': now}
            changed = current.model_copy(
                update={
                    **(updates or {}),
                    **runtime_updates,
                    'state': target,
                    'version': int(row['version']) + 1,
                    'updated_at': now,
                }
            )
            cursor = connection.execute(
                '''
                UPDATE runs
                SET state = ?, version = ?, payload = ?, updated_at = ?
                WHERE run_id = ? AND version = ?
                ''',
                (
                    target.value,
                    changed.version,
                    _dump(changed),
                    now.isoformat(),
                    run_id,
                    row['version'],
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrencyConflict(f'run was updated concurrently: {run_id}')
            self._append_event_conn(
                connection,
                run_id=run_id,
                source=source,
                event_type='run.state_changed',
                payload={
                    'from': current.state.value,
                    'to': target.value,
                    **(payload or {}),
                },
            )
        return changed

    def save_turn(self, record: TurnRecord) -> TurnRecord:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT INTO turns (
                    turn_id, run_id, status, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    status = excluded.status,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                ''',
                (
                    record.turn_id,
                    record.run_id,
                    record.status,
                    _dump(record),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def list_turns(self, run_id: str) -> list[TurnRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT payload FROM turns WHERE run_id = ? ORDER BY created_at',
                (run_id,),
            ).fetchall()
        return [TurnRecord.model_validate_json(row['payload']) for row in rows]

    def mark_running_turns_interrupted(self, run_id: str) -> int:
        changed = 0
        for turn in self.list_turns(run_id):
            if turn.status != 'running':
                continue
            updated = turn.model_copy(
                update={
                    'status': 'failed',
                    'error': 'orchestrator restarted during active agent turn',
                    'updated_at': utc_now(),
                }
            )
            self.save_turn(updated)
            changed += 1
        return changed

    def save_action(self, record: ActionRecord) -> ActionRecord:
        with self.transaction() as connection:
            existing = connection.execute(
                'SELECT payload FROM actions WHERE idempotency_key = ?',
                (record.idempotency_key,),
            ).fetchone()
            if existing is not None:
                return ActionRecord.model_validate_json(existing['payload'])
            connection.execute(
                '''
                INSERT INTO actions (
                    action_id, run_id, approval_status, idempotency_key,
                    payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.action_id,
                    record.run_id,
                    record.approval_status.value,
                    record.idempotency_key,
                    _dump(record),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def update_action(
        self,
        action_id: str,
        *,
        approval_status: ApprovalStatus,
        reviewer: str,
        reason: str,
    ) -> ActionRecord:
        with self.transaction() as connection:
            row = connection.execute(
                'SELECT payload FROM actions WHERE action_id = ?',
                (action_id,),
            ).fetchone()
            if row is None:
                raise RecordNotFound(action_id)
            action = ActionRecord.model_validate_json(row['payload'])
            if action.approval_status not in {
                ApprovalStatus.PENDING,
                ApprovalStatus.AUTOMATICALLY_APPROVED,
            }:
                raise ConcurrencyConflict(
                    f'action is already terminal: {action.approval_status}'
                )
            updated = action.model_copy(
                update={
                    'approval_status': approval_status,
                    'reviewer': reviewer,
                    'reason': reason,
                    'updated_at': utc_now(),
                }
            )
            connection.execute(
                '''
                UPDATE actions
                SET approval_status = ?, payload = ?, updated_at = ?
                WHERE action_id = ?
                ''',
                (
                    updated.approval_status.value,
                    _dump(updated),
                    updated.updated_at.isoformat(),
                    action_id,
                ),
            )
        return updated

    def mark_action_honeydew_approved(
        self,
        action_id: str,
        *,
        review_turn_id: str,
    ) -> ActionRecord:
        with self.transaction() as connection:
            row = connection.execute(
                'SELECT payload FROM actions WHERE action_id = ?',
                (action_id,),
            ).fetchone()
            if row is None:
                raise RecordNotFound(action_id)
            action = ActionRecord.model_validate_json(row['payload'])
            if action.approval_status != ApprovalStatus.PENDING:
                raise ConcurrencyConflict(
                    f'action is not pending: {action.approval_status}'
                )
            updated = action.model_copy(
                update={
                    'honeydew_approved': True,
                    'honeydew_review_turn_id': review_turn_id,
                    'updated_at': utc_now(),
                }
            )
            connection.execute(
                '''
                UPDATE actions
                SET payload = ?, updated_at = ?
                WHERE action_id = ?
                ''',
                (
                    _dump(updated),
                    updated.updated_at.isoformat(),
                    action_id,
                ),
            )
        return updated

    def mark_action_execution_failed(
        self,
        action_id: str,
        *,
        reason: str,
    ) -> ActionRecord:
        with self.transaction() as connection:
            row = connection.execute(
                'SELECT payload FROM actions WHERE action_id = ?',
                (action_id,),
            ).fetchone()
            if row is None:
                raise RecordNotFound(action_id)
            action = ActionRecord.model_validate_json(row['payload'])
            if action.approval_status != ApprovalStatus.APPROVED:
                raise ConcurrencyConflict(
                    f'action is not approved: {action.approval_status}'
                )
            updated = action.model_copy(
                update={
                    'approval_status': ApprovalStatus.EXECUTION_FAILED,
                    'reason': reason,
                    'updated_at': utc_now(),
                }
            )
            connection.execute(
                '''
                UPDATE actions
                SET approval_status = ?, payload = ?, updated_at = ?
                WHERE action_id = ?
                ''',
                (
                    updated.approval_status.value,
                    _dump(updated),
                    updated.updated_at.isoformat(),
                    action_id,
                ),
            )
        return updated

    def get_action(self, action_id: str) -> ActionRecord:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload FROM actions WHERE action_id = ?',
                (action_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(action_id)
        return ActionRecord.model_validate_json(row['payload'])

    def list_actions(self, run_id: str) -> list[ActionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT payload FROM actions WHERE run_id = ? ORDER BY created_at',
                (run_id,),
            ).fetchall()
        return [ActionRecord.model_validate_json(row['payload']) for row in rows]

    def create_job_if_absent(self, record: JobRecord) -> tuple[JobRecord, bool]:
        with self.transaction() as connection:
            existing = connection.execute(
                'SELECT payload FROM jobs WHERE idempotency_key = ?',
                (record.idempotency_key,),
            ).fetchone()
            if existing is not None:
                return JobRecord.model_validate_json(existing['payload']), False
            connection.execute(
                '''
                INSERT INTO jobs (
                    job_id, run_id, action_id, status, idempotency_key,
                    payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.job_id,
                    record.run_id,
                    record.action_id,
                    record.status.value,
                    record.idempotency_key,
                    _dump(record),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record, True

    def update_job(self, record: JobRecord) -> JobRecord:
        updated = record.model_copy(update={'updated_at': utc_now()})
        with self.transaction() as connection:
            cursor = connection.execute(
                '''
                UPDATE jobs
                SET status = ?, payload = ?, updated_at = ?
                WHERE job_id = ?
                ''',
                (
                    updated.status.value,
                    _dump(updated),
                    updated.updated_at.isoformat(),
                    updated.job_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RecordNotFound(updated.job_id)
        return updated

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload FROM jobs WHERE job_id = ?',
                (job_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(job_id)
        return JobRecord.model_validate_json(row['payload'])

    def list_jobs(
        self,
        run_id: str,
        *,
        statuses: Iterable[JobStatus] | None = None,
    ) -> list[JobRecord]:
        parameters: list[Any] = [run_id]
        query = 'SELECT payload FROM jobs WHERE run_id = ?'
        if statuses:
            values = [status.value for status in statuses]
            query += ' AND status IN (' + ','.join('?' for _ in values) + ')'
            parameters.extend(values)
        query += ' ORDER BY created_at, job_id'
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [JobRecord.model_validate_json(row['payload']) for row in rows]

    def save_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT OR IGNORE INTO artifacts (
                    artifact_id, run_id, job_id, payload, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    record.artifact_id,
                    record.run_id,
                    record.job_id,
                    _dump(record),
                    record.created_at.isoformat(),
                ),
            )
        return record

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT payload FROM artifacts
                WHERE run_id = ? ORDER BY created_at, artifact_id
                ''',
                (run_id,),
            ).fetchall()
        return [ArtifactRecord.model_validate_json(row['payload']) for row in rows]

    def save_dataset(
        self,
        record: IngestedDatasetRecord,
    ) -> IngestedDatasetRecord:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT OR IGNORE INTO datasets (
                    dataset_id, payload, created_at
                ) VALUES (?, ?, ?)
                ''',
                (
                    record.dataset_id,
                    _dump(record),
                    record.created_at.isoformat(),
                ),
            )
        return self.get_dataset(record.dataset_id)

    def get_dataset(self, dataset_id: str) -> IngestedDatasetRecord:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload FROM datasets WHERE dataset_id = ?',
                (dataset_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(dataset_id)
        return IngestedDatasetRecord.model_validate_json(row['payload'])

    def list_datasets(self) -> list[IngestedDatasetRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT payload FROM datasets ORDER BY created_at, dataset_id'
            ).fetchall()
        return [
            IngestedDatasetRecord.model_validate_json(row['payload'])
            for row in rows
        ]

    def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[EventRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT payload FROM events
                WHERE run_id = ? AND sequence_number > ?
                ORDER BY sequence_number
                ''',
                (run_id, after_sequence),
            ).fetchall()
        return [EventRecord.model_validate_json(row['payload']) for row in rows]

    def save_knowledge_source(self, record: KnowledgeSource) -> KnowledgeSource:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT INTO knowledge_sources (
                    source_id, source_type, canonical_uri, run_scope,
                    access_policy, source_version, digest, ingested_at,
                    index_version, title, metadata, parent_source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_type = excluded.source_type,
                    canonical_uri = excluded.canonical_uri,
                    run_scope = excluded.run_scope,
                    access_policy = excluded.access_policy,
                    source_version = excluded.source_version,
                    digest = excluded.digest,
                    ingested_at = excluded.ingested_at,
                    index_version = excluded.index_version,
                    title = excluded.title,
                    metadata = excluded.metadata,
                    parent_source_id = excluded.parent_source_id
                ''',
                (
                    record.source_id,
                    record.source_type.value,
                    record.canonical_uri,
                    record.run_scope,
                    record.access_policy,
                    record.source_version,
                    record.digest,
                    record.ingested_at.isoformat(),
                    record.index_version,
                    record.title,
                    json.dumps(record.metadata, sort_keys=True),
                    record.parent_source_id,
                ),
            )
        return record

    def get_knowledge_source(self, source_id: str) -> KnowledgeSource:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM knowledge_sources WHERE source_id = ?',
                (source_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(source_id)
        return self._knowledge_source_from_row(row)

    def find_knowledge_source(
        self,
        *,
        digest: str,
        canonical_uri: str,
    ) -> KnowledgeSource | None:
        """Resolve an existing source by content digest and canonical URI.

        Used by ingestion to deduplicate re-ingested approved sources: identical
        content from the same URI returns the original row instead of creating a
        second source with a new evidence URI.
        """
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM knowledge_sources '
                'WHERE digest = ? AND canonical_uri = ?',
                (digest, canonical_uri),
            ).fetchone()
        if row is None:
            return None
        return self._knowledge_source_from_row(row)

    def list_knowledge_sources(
        self,
        *,
        source_types: Iterable[SourceType] | None = None,
        run_scope: str | None = None,
    ) -> list[KnowledgeSource]:
        parameters: list[Any] = []
        query = 'SELECT * FROM knowledge_sources'
        clauses: list[str] = []
        if run_scope is not None:
            clauses.append('(run_scope = ? OR run_scope IS NULL)')
            parameters.append(run_scope)
        if source_types:
            values = [item.value for item in source_types]
            clauses.append(
                'source_type IN (' + ','.join('?' for _ in values) + ')'
            )
            parameters.extend(values)
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        query += ' ORDER BY ingested_at, source_id'
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._knowledge_source_from_row(row) for row in rows]

    @staticmethod
    def _knowledge_source_from_row(row: sqlite3.Row) -> KnowledgeSource:
        return KnowledgeSource(
            source_id=row['source_id'],
            source_type=SourceType(row['source_type']),
            canonical_uri=row['canonical_uri'],
            run_scope=row['run_scope'],
            access_policy=row['access_policy'],
            source_version=row['source_version'],
            digest=row['digest'],
            ingested_at=datetime.fromisoformat(row['ingested_at']),
            index_version=row['index_version'],
            title=row['title'],
            metadata=json.loads(row['metadata']),
            parent_source_id=row['parent_source_id'],
        )

    def delete_knowledge_source(self, source_id: str) -> bool:
        with self.transaction() as connection:
            connection.execute(
                'DELETE FROM knowledge_chunks_fts '
                'WHERE chunk_id IN ('
                '  SELECT chunk_id FROM knowledge_chunks WHERE source_id = ?'
                ')',
                (source_id,),
            )
            cursor = connection.execute(
                'DELETE FROM knowledge_sources WHERE source_id = ?',
                (source_id,),
            )
        return cursor.rowcount == 1

    def delete_knowledge_sources_by_digest(self, digest: str) -> int:
        with self.transaction() as connection:
            connection.execute(
                'DELETE FROM knowledge_chunks_fts '
                'WHERE chunk_id IN ('
                '  SELECT chunk_id FROM knowledge_chunks WHERE source_id IN ('
                '    SELECT source_id FROM knowledge_sources WHERE digest = ?'
                '  )'
                ')',
                (digest,),
            )
            cursor = connection.execute(
                'DELETE FROM knowledge_sources WHERE digest = ?',
                (digest,),
            )
        return cursor.rowcount

    def replace_knowledge_chunks(
        self,
        source_id: str,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        with self.transaction() as connection:
            connection.execute(
                'DELETE FROM knowledge_chunks_fts '
                'WHERE chunk_id IN ('
                '  SELECT chunk_id FROM knowledge_chunks WHERE source_id = ?'
                ')',
                (source_id,),
            )
            connection.execute(
                'DELETE FROM knowledge_chunks WHERE source_id = ?',
                (source_id,),
            )
            for chunk in chunks:
                connection.execute(
                    '''
                    INSERT INTO knowledge_chunks (
                        chunk_id, source_id, chunk_index, text, digest,
                        token_count, index_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.digest,
                        chunk.token_count,
                        chunk.index_version,
                    ),
                )
                connection.execute(
                    '''
                    INSERT INTO knowledge_chunks_fts (chunk_id, text)
                    VALUES (?, ?)
                    ''',
                    (chunk.chunk_id, chunk.text),
                )
        return chunks

    def list_knowledge_chunks(
        self,
        source_id: str,
    ) -> list[KnowledgeChunk]:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM knowledge_chunks
                WHERE source_id = ? ORDER BY chunk_index
                ''',
                (source_id,),
            ).fetchall()
        return [
            KnowledgeChunk(
                chunk_id=row['chunk_id'],
                source_id=row['source_id'],
                chunk_index=row['chunk_index'],
                text=row['text'],
                digest=row['digest'],
                token_count=row['token_count'],
                index_version=row['index_version'],
            )
            for row in rows
        ]

    def search_knowledge_chunks(
        self,
        query: str,
        *,
        source_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        terms = [term for term in query.split() if len(term) > 1]
        fts_query = ' OR '.join(f'"{term}"' for term in terms[:6]) or None
        with self._connect() as connection:
            if fts_query and source_ids:
                placeholders = ', '.join('?' * len(source_ids))
                rows = connection.execute(
                    f'''
                    SELECT c.chunk_id, c.source_id, c.chunk_index, c.text,
                           c.digest, c.token_count, c.index_version,
                           bm25(knowledge_chunks_fts) AS rank
                    FROM knowledge_chunks c
                    JOIN knowledge_chunks_fts
                      ON knowledge_chunks_fts.chunk_id = c.chunk_id
                    WHERE knowledge_chunks_fts MATCH ?
                      AND c.source_id IN ({placeholders})
                    ORDER BY rank
                    LIMIT ?
                    ''',
                    (fts_query, *source_ids, limit * 3),
                ).fetchall()
            elif fts_query:
                rows = connection.execute(
                    '''
                    SELECT c.chunk_id, c.source_id, c.chunk_index, c.text,
                           c.digest, c.token_count, c.index_version,
                           bm25(knowledge_chunks_fts) AS rank
                    FROM knowledge_chunks c
                    JOIN knowledge_chunks_fts
                      ON knowledge_chunks_fts.chunk_id = c.chunk_id
                    WHERE knowledge_chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    ''',
                    (fts_query, limit * 3),
                ).fetchall()
            else:
                rows = []
        return [
            {
                'chunk_id': row['chunk_id'],
                'source_id': row['source_id'],
                'chunk_index': row['chunk_index'],
                'text': row['text'],
                'digest': row['digest'],
                'token_count': row['token_count'],
                'index_version': row['index_version'],
                'rank': row['rank'],
            }
            for row in rows[:limit]
        ]

    def save_context_packet(self, packet: ContextPacket) -> ContextPacket:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT INTO context_packets (
                    packet_id, run_id, agent, turn_number, turn_kind, query,
                    index_version, ranked_sources, exact_text_supplied,
                    token_budget, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    packet.packet_id,
                    packet.run_id,
                    packet.agent.value,
                    packet.turn_number,
                    packet.turn_kind.value,
                    packet.query,
                    packet.index_version,
                    json.dumps(packet.ranked_sources),
                    packet.exact_text_supplied,
                    packet.token_budget,
                    packet.created_at.isoformat(),
                ),
            )
        return packet

    def get_context_packet(self, packet_id: str) -> ContextPacket:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM context_packets WHERE packet_id = ?',
                (packet_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(packet_id)
        return ContextPacket(
            packet_id=row['packet_id'],
            run_id=row['run_id'],
            agent=AgentName(row['agent']),
            turn_number=row['turn_number'],
            turn_kind=TurnKind(row['turn_kind']),
            query=row['query'],
            index_version=row['index_version'],
            ranked_sources=json.loads(row['ranked_sources']),
            exact_text_supplied=row['exact_text_supplied'],
            token_budget=row['token_budget'],
            created_at=datetime.fromisoformat(row['created_at']),
        )

    def list_context_packets(self, run_id: str) -> list[ContextPacket]:
        with self._connect() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM context_packets
                WHERE run_id = ? ORDER BY created_at, packet_id
                ''',
                (run_id,),
            ).fetchall()
        return [self._context_packet_from_row(row) for row in rows]

    @staticmethod
    def _context_packet_from_row(row: sqlite3.Row) -> ContextPacket:
        return ContextPacket(
            packet_id=row['packet_id'],
            run_id=row['run_id'],
            agent=AgentName(row['agent']),
            turn_number=row['turn_number'],
            turn_kind=TurnKind(row['turn_kind']),
            query=row['query'],
            index_version=row['index_version'],
            ranked_sources=json.loads(row['ranked_sources']),
            exact_text_supplied=row['exact_text_supplied'],
            token_budget=row['token_budget'],
            created_at=datetime.fromisoformat(row['created_at']),
        )
