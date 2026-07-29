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
    EventRecord,
    JobRecord,
    JobStatus,
    RunRecord,
    RunState,
    TERMINAL_STATES,
    TurnRecord,
    utc_now,
)
from .state_machine import validate_transition


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
            changed = current.model_copy(
                update={
                    **(updates or {}),
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
