from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .schemas import ArtifactRef, ExperimentLogEntry, ExperimentRecord, PlannerSpec, ValidationResult


class StateStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    planner_source TEXT,
                    planner_raw_output TEXT,
                    normalized_spec_json TEXT,
                    validation_json TEXT,
                    job_name TEXT,
                    result_summary TEXT,
                    artifact_refs_json TEXT,
                    error_message TEXT,
                    submitted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    FOREIGN KEY (experiment_id) REFERENCES experiments (id)
                );
                """
            )

    def create_experiment(self, request_text: str, trace_id: str) -> ExperimentRecord:
        experiment_id = uuid.uuid4().hex
        now = _utcnow()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiments (
                    id,
                    trace_id,
                    request_text,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (experiment_id, trace_id, request_text, 'received', now, now),
            )
        return self.get_experiment(experiment_id)

    def update_experiment(self, experiment_id: str, **fields: Any) -> ExperimentRecord:
        if not fields:
            return self.get_experiment(experiment_id)

        column_aliases = {
            'normalized_spec': 'normalized_spec_json',
            'validation': 'validation_json',
            'artifact_refs': 'artifact_refs_json',
        }
        db_fields = {column_aliases.get(key, key): value for key, value in fields.items()}
        db_fields['updated_at'] = _utcnow()
        assignments = ', '.join(f'{column} = ?' for column in db_fields)
        values = [self._serialize(value) for value in db_fields.values()]
        values.append(experiment_id)

        with self._connect() as connection:
            connection.execute(
                f'UPDATE experiments SET {assignments} WHERE id = ?',
                values,
            )
        return self.get_experiment(experiment_id)

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM experiments WHERE id = ?',
                (experiment_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_experiment(row)

    def append_log(
        self,
        experiment_id: str,
        level: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_logs (
                    experiment_id,
                    timestamp,
                    level,
                    message,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    _utcnow(),
                    level.upper(),
                    message,
                    json.dumps(payload, sort_keys=True) if payload is not None else None,
                ),
            )

    def get_logs(self, experiment_id: str) -> list[ExperimentLogEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT timestamp, level, message, payload_json FROM experiment_logs WHERE experiment_id = ? ORDER BY id ASC',
                (experiment_id,),
            ).fetchall()
        return [
            ExperimentLogEntry(
                timestamp=_parse_datetime(row['timestamp']),
                level=row['level'],
                message=row['message'],
                payload=json.loads(row['payload_json']) if row['payload_json'] else None,
            )
            for row in rows
        ]

    def get_latest_successful(self, pipeline: str, dataset: str) -> ExperimentRecord | None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM experiments
                WHERE status = 'succeeded'
                  AND normalized_spec_json IS NOT NULL
                ORDER BY submitted_at DESC, created_at DESC
                """
            ).fetchall()
        for row in rows:
            record = self._row_to_experiment(row)
            if record.normalized_spec and record.normalized_spec.pipeline == pipeline and record.normalized_spec.dataset == dataset:
                return record
        return None

    def _row_to_experiment(self, row: sqlite3.Row) -> ExperimentRecord:
        return ExperimentRecord(
            id=row['id'],
            trace_id=row['trace_id'],
            request_text=row['request_text'],
            status=row['status'],
            planner_source=row['planner_source'],
            planner_raw_output=row['planner_raw_output'],
            normalized_spec=self._load_model(row['normalized_spec_json'], PlannerSpec),
            validation=self._load_model(row['validation_json'], ValidationResult),
            job_name=row['job_name'],
            result_summary=row['result_summary'],
            artifact_refs=self._load_artifacts(row['artifact_refs_json']),
            error_message=row['error_message'],
            submitted_at=_parse_datetime(row['submitted_at']),
            created_at=_parse_datetime(row['created_at']),
            updated_at=_parse_datetime(row['updated_at']),
        )

    def _load_model(self, payload: str | None, model_type: type[BaseModel]) -> BaseModel | None:
        if payload is None:
            return None
        return model_type.model_validate_json(payload)

    def _load_artifacts(self, payload: str | None) -> list[ArtifactRef]:
        if payload is None:
            return []
        return [ArtifactRef.model_validate(item) for item in json.loads(payload)]

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        if isinstance(value, list):
            if not value:
                return json.dumps([])
            if isinstance(value[0], BaseModel):
                return json.dumps([item.model_dump(mode='json') for item in value])
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
