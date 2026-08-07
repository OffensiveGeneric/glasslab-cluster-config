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
    ApprovalStatus,
    ArtifactRecord,
    ContextPacketRecord,
    EventRecord,
    IngestedDatasetRecord,
    JobRecord,
    JobStatus,
    KnowledgeEvent,
    RunRecord,
    RunState,
    SourceRecord,
    SourceType,
    TERMINAL_STATES,
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

                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    canonical_uri TEXT NOT NULL,
                    run_scope TEXT,
                    access_policy TEXT NOT NULL,
                    source_version TEXT,
                    content_digest TEXT NOT NULL,
                    ingestion_timestamp TEXT NOT NULL,
                    chunking_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    parent_source_id TEXT,
                    chunk_index INTEGER,
                    total_chunks INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS knowledge_sources_type_idx
                ON knowledge_sources(source_type);
                CREATE INDEX IF NOT EXISTS knowledge_sources_digest_idx
                ON knowledge_sources(content_digest);
                CREATE INDEX IF NOT EXISTS knowledge_sources_run_scope_idx
                ON knowledge_sources(run_scope);

                CREATE TABLE IF NOT EXISTS context_packets (
                    packet_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    agent TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    turn_kind TEXT NOT NULL,
                    query_or_retrieval_intent TEXT NOT NULL,
                    index_version TEXT NOT NULL,
                    source_ids_with_scores TEXT NOT NULL,
                    exact_text_supplied TEXT NOT NULL,
                    token_budget INTEGER NOT NULL,
                    used_tokens INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS context_packets_run_idx
                ON context_packets(run_id, turn_number, agent);
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

    def ingest_source(self, record: SourceRecord) -> SourceRecord:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT OR IGNORE INTO knowledge_sources (
                    source_id, source_type, canonical_uri, run_scope, access_policy,
                    source_version, content_digest, ingestion_timestamp, chunking_version,
                    title, metadata, parent_source_id, chunk_index, total_chunks, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.source_id,
                    record.source_type.value,
                    record.canonical_uri,
                    record.run_scope,
                    record.access_policy,
                    record.source_version,
                    record.content_digest,
                    record.ingestion_timestamp.isoformat(),
                    record.chunking_version,
                    record.title,
                    json.dumps(record.metadata),
                    record.parent_source_id,
                    record.chunk_index,
                    record.total_chunks,
                    record.created_at.isoformat(),
                ),
            )
        return self.get_source(record.source_id)

    def get_source(self, source_id: str) -> SourceRecord:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM knowledge_sources WHERE source_id = ?',
                (source_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(source_id)
        return SourceRecord(
            source_id=row['source_id'],
            source_type=SourceType(row['source_type']),
            canonical_uri=row['canonical_uri'],
            run_scope=row['run_scope'],
            access_policy=row['access_policy'],
            source_version=row['source_version'],
            content_digest=row['content_digest'],
            ingestion_timestamp=datetime.fromisoformat(row['ingestion_timestamp']),
            chunking_version=row['chunking_version'],
            title=row['title'],
            metadata=json.loads(row['metadata']),
            parent_source_id=row['parent_source_id'],
            chunk_index=row['chunk_index'],
            total_chunks=row['total_chunks'],
            created_at=datetime.fromisoformat(row['created_at']),
        )

    def get_source_by_digest(self, content_digest: str) -> SourceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM knowledge_sources WHERE content_digest = ?',
                (content_digest,),
            ).fetchone()
        if row is None:
            return None
        return SourceRecord(
            source_id=row['source_id'],
            source_type=SourceType(row['source_type']),
            canonical_uri=row['canonical_uri'],
            run_scope=row['run_scope'],
            access_policy=row['access_policy'],
            source_version=row['source_version'],
            content_digest=row['content_digest'],
            ingestion_timestamp=datetime.fromisoformat(row['ingestion_timestamp']),
            chunking_version=row['chunking_version'],
            title=row['title'],
            metadata=json.loads(row['metadata']),
            parent_source_id=row['parent_source_id'],
            chunk_index=row['chunk_index'],
            total_chunks=row['total_chunks'],
            created_at=datetime.fromisoformat(row['created_at']),
        )

    def list_sources(
        self,
        *,
        source_type: SourceType | None = None,
        run_scope: str | None = None,
    ) -> list[SourceRecord]:
        parameters: list[Any] = []
        query = 'SELECT * FROM knowledge_sources'
        conditions: list[str] = []
        if source_type:
            conditions.append('source_type = ?')
            parameters.append(source_type.value)
        if run_scope:
            conditions.append('run_scope = ?')
            parameters.append(run_scope)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY created_at DESC'
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._source_from_row(row) for row in rows]

    def _source_from_row(self, row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source_id=row['source_id'],
            source_type=SourceType(row['source_type']),
            canonical_uri=row['canonical_uri'],
            run_scope=row['run_scope'],
            access_policy=row['access_policy'],
            source_version=row['source_version'],
            content_digest=row['content_digest'],
            ingestion_timestamp=datetime.fromisoformat(row['ingestion_timestamp']),
            chunking_version=row['chunking_version'],
            title=row['title'],
            metadata=json.loads(row['metadata']),
            parent_source_id=row['parent_source_id'],
            chunk_index=row['chunk_index'],
            total_chunks=row['total_chunks'],
            created_at=datetime.fromisoformat(row['created_at']),
        )

    def delete_source(self, source_id: str) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                'DELETE FROM knowledge_sources WHERE source_id = ?',
                (source_id,),
            )
            return cursor.rowcount

    def save_context_packet(self, record: ContextPacketRecord) -> ContextPacketRecord:
        with self.transaction() as connection:
            connection.execute(
                '''
                INSERT INTO context_packets (
                    packet_id, run_id, agent, turn_number, turn_kind,
                    query_or_retrieval_intent, index_version, source_ids_with_scores,
                    exact_text_supplied, token_budget, used_tokens, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    record.packet_id,
                    record.run_id,
                    record.agent,
                    record.turn_number,
                    record.turn_kind,
                    record.query_or_retrieval_intent,
                    record.index_version,
                    json.dumps(record.source_ids_with_scores),
                    record.exact_text_supplied,
                    record.token_budget,
                    record.used_tokens,
                    record.timestamp.isoformat(),
                ),
            )
        return record

    def get_context_packet(self, packet_id: str) -> ContextPacketRecord:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM context_packets WHERE packet_id = ?',
                (packet_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(packet_id)
        return ContextPacketRecord(
            packet_id=row['packet_id'],
            run_id=row['run_id'],
            agent=row['agent'],
            turn_number=row['turn_number'],
            turn_kind=row['turn_kind'],
            query_or_retrieval_intent=row['query_or_retrieval_intent'],
            index_version=row['index_version'],
            source_ids_with_scores=json.loads(row['source_ids_with_scores']),
            exact_text_supplied=row['exact_text_supplied'],
            token_budget=row['token_budget'],
            used_tokens=row['used_tokens'],
            timestamp=datetime.fromisoformat(row['timestamp']),
        )

    def list_context_packets(
        self,
        run_id: str,
        *,
        agent: str | None = None,
        turn_number: int | None = None,
    ) -> list[ContextPacketRecord]:
        parameters: list[Any] = [run_id]
        query = 'SELECT * FROM context_packets WHERE run_id = ?'
        if agent:
            query += ' AND agent = ?'
            parameters.append(agent)
        if turn_number is not None:
            query += ' AND turn_number = ?'
            parameters.append(turn_number)
        query += ' ORDER BY timestamp DESC'
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._context_packet_from_row(row) for row in rows]

    def _context_packet_from_row(self, row: sqlite3.Row) -> ContextPacketRecord:
        return ContextPacketRecord(
            packet_id=row['packet_id'],
            run_id=row['run_id'],
            agent=row['agent'],
            turn_number=row['turn_number'],
            turn_kind=row['turn_kind'],
            query_or_retrieval_intent=row['query_or_retrieval_intent'],
            index_version=row['index_version'],
            source_ids_with_scores=json.loads(row['source_ids_with_scores']),
            exact_text_supplied=row['exact_text_supplied'],
            token_budget=row['token_budget'],
            used_tokens=row['used_tokens'],
            timestamp=datetime.fromisoformat(row['timestamp']),
        )


    def retrieve_context(
        self,
        *,
        run_id: str,
        agent: str,
        turn_kind: str,
        query: str,
        index_version: str = 'v1',
        max_results: int = 10,
        token_budget: int = 4000,
        run_scope: str | None = None,
        source_types: list[SourceType] | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Retrieve context matching the query within allowed scopes.

        Returns:
            Tuple of (source_ids_with_scores, exact_text_supplied)
        """
        conditions: list[Any] = []
        
        # Filter by run_scope if provided (run_scope is the only scope column in knowledge_sources)
        if run_scope:
            conditions.append('run_scope = ?')
            parameters = [run_scope]
        else:
            # No run_scope means all public/global sources (run_scope IS NULL)
            conditions.append('run_scope IS NULL')
            parameters = []
        
        if source_types:
            type_placeholders = ', '.join(['?'] * len(source_types))
            conditions.append(f'source_type IN ({type_placeholders})')
            for st in source_types:
                parameters.append(st.value)
        
        query_clause = ' AND '.join(conditions)
        
        with self._connect() as connection:
            rows = connection.execute(
                f'SELECT * FROM knowledge_sources WHERE {query_clause}',
                parameters,
            ).fetchall()
        
        scored_sources: list[dict[str, Any]] = []
        for row in rows:
            score = self._compute_relevance_score(
                row=row,
                query=query,
                agent=agent,
                turn_kind=turn_kind,
            )
            if score > 0:
                scored_sources.append({
                    'source_id': row['source_id'],
                    'score': score,
                })
        
        scored_sources.sort(key=lambda x: x['score'], reverse=True)
        top_sources = scored_sources[:max_results]
        
        chunks_text = []
        used_tokens = 0
        
        for source in top_sources:
            try:
                source_record = self.get_source(source['source_id'])
                # Check if this is a chunked source
                if source_record.chunk_index is not None and source_record.total_chunks is not None:
                    chunk_text = self._get_chunk_content(
                        source_record=source_record,
                    )
                    chunk_tokens = len(chunk_text) // 4
                    if used_tokens + chunk_tokens <= token_budget:
                        chunks_text.append(chunk_text)
                        used_tokens += chunk_tokens
                else:
                    # Non-chunked source: use title and summary
                    title = source_record.title
                    summary = self._get_chunk_content(source_record=source_record)
                    if summary:
                        chunk_text = f"{title}\n\n{summary}"
                    else:
                        chunk_text = title
                    chunk_tokens = len(chunk_text) // 4
                    if used_tokens + chunk_tokens <= token_budget:
                        chunks_text.append(chunk_text)
                        used_tokens += chunk_tokens
            except RecordNotFound:
                continue
        
        exact_text_supplied = '\n\n'.join(chunks_text)
        
        return top_sources, exact_text_supplied

    def _compute_relevance_score(
        self,
        *,
        row: sqlite3.Row,
        query: str,
        agent: str,
        turn_kind: str,
    ) -> float:
        """Compute relevance score for a source."""
        score = 0.0
        
        title = row['title'].lower()
        canonical_uri = row['canonical_uri'].lower()
        
        query_lower = query.lower()
        
        if query_lower in title:
            score += 10.0
        if query_lower in canonical_uri:
            score += 5.0
        
        source_type = row['source_type']
        
        if source_type == 'handoff' and agent in ('honeydew', 'beaker'):
            score += 3.0
        if source_type == 'protocol' and agent == 'honeydew':
            score += 3.0
        if source_type == 'implementation' and agent == 'beaker':
            score += 3.0
        
        access_policy = row['access_policy']
        if access_policy == 'public':
            score += 1.0
        
        if row['source_version'] and row['source_version'].startswith('v'):
            score += 0.5
        
        return score

    def _get_chunk_content(self, *, source_record: SourceRecord) -> str:
        """Get content for a chunk."""
        metadata = source_record.metadata
        if 'chunk_content' in metadata:
            return metadata['chunk_content']
        if 'content' in metadata:
            return metadata['content']
        if 'text' in metadata:
            return metadata['text']
        return metadata.get('summary', '')
