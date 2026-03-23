from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock

from services.common.schemas import ArtifactsIndex

from .schemas import IntakeRecord, LogEntry, RunRecord


class RunStore(ABC):
    @abstractmethod
    def save_intake(self, record: IntakeRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_intake(self, intake_id: str) -> IntakeRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_intake(self) -> IntakeRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_run(self, record: RunRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> RunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_artifacts(self, run_id: str, artifacts: ArtifactsIndex) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_artifacts(self, run_id: str) -> ArtifactsIndex | None:
        raise NotImplementedError

    @abstractmethod
    def append_log(self, run_id: str, entry: LogEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_logs(self, run_id: str) -> list[LogEntry]:
        raise NotImplementedError


class InMemoryRunStore(RunStore):
    def __init__(self) -> None:
        self._intakes: dict[str, IntakeRecord] = {}
        self._latest_intake_id: str | None = None
        self._runs: dict[str, RunRecord] = {}
        self._artifacts: dict[str, ArtifactsIndex] = {}
        self._logs: dict[str, list[LogEntry]] = {}
        self._lock = Lock()

    def save_intake(self, record: IntakeRecord) -> None:
        with self._lock:
            self._intakes[record.intake_id] = record
            self._latest_intake_id = record.intake_id

    def get_intake(self, intake_id: str) -> IntakeRecord | None:
        with self._lock:
            return self._intakes.get(intake_id)

    def get_latest_intake(self) -> IntakeRecord | None:
        with self._lock:
            if self._latest_intake_id is None:
                return None
            return self._intakes.get(self._latest_intake_id)

    def save_run(self, record: RunRecord) -> None:
        with self._lock:
            self._runs[record.run_id] = record

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def save_artifacts(self, run_id: str, artifacts: ArtifactsIndex) -> None:
        with self._lock:
            self._artifacts[run_id] = artifacts

    def get_artifacts(self, run_id: str) -> ArtifactsIndex | None:
        with self._lock:
            return self._artifacts.get(run_id)

    def append_log(self, run_id: str, entry: LogEntry) -> None:
        with self._lock:
            self._logs.setdefault(run_id, []).append(entry)

    def get_logs(self, run_id: str) -> list[LogEntry]:
        with self._lock:
            return list(self._logs.get(run_id, []))
