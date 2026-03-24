from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock

from services.common.schemas import ArtifactsIndex

from .schemas import (
    DesignDraftRecord,
    IntakeRecord,
    InterpretationRecord,
    LogEntry,
    ReplicabilityAssessmentRecord,
    RunRecord,
    ScheduledOperationRecord,
)


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
    def save_design_draft(self, record: DesignDraftRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_design_draft(self, design_id: str) -> DesignDraftRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_design_draft(self) -> DesignDraftRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_interpretation(self, record: InterpretationRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_interpretation(self, interpretation_id: str) -> InterpretationRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_interpretation(self) -> InterpretationRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_replicability_assessment(self, record: ReplicabilityAssessmentRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_replicability_assessment(self, assessment_id: str) -> ReplicabilityAssessmentRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_replicability_assessment(self) -> ReplicabilityAssessmentRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_run(self, record: RunRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> RunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_run(self) -> RunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_schedule(self, record: ScheduledOperationRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_schedule(self, schedule_id: str) -> ScheduledOperationRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_schedules(self, operation_type: str | None = None) -> list[ScheduledOperationRecord]:
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
        self._interpretations: dict[str, InterpretationRecord] = {}
        self._latest_interpretation_id: str | None = None
        self._replicability_assessments: dict[str, ReplicabilityAssessmentRecord] = {}
        self._latest_replicability_assessment_id: str | None = None
        self._design_drafts: dict[str, DesignDraftRecord] = {}
        self._latest_design_draft_id: str | None = None
        self._runs: dict[str, RunRecord] = {}
        self._latest_run_id: str | None = None
        self._schedules: dict[str, ScheduledOperationRecord] = {}
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

    def save_interpretation(self, record: InterpretationRecord) -> None:
        with self._lock:
            self._interpretations[record.interpretation_id] = record
            self._latest_interpretation_id = record.interpretation_id

    def get_interpretation(self, interpretation_id: str) -> InterpretationRecord | None:
        with self._lock:
            return self._interpretations.get(interpretation_id)

    def get_latest_interpretation(self) -> InterpretationRecord | None:
        with self._lock:
            if self._latest_interpretation_id is None:
                return None
            return self._interpretations.get(self._latest_interpretation_id)

    def save_replicability_assessment(self, record: ReplicabilityAssessmentRecord) -> None:
        with self._lock:
            self._replicability_assessments[record.assessment_id] = record
            self._latest_replicability_assessment_id = record.assessment_id

    def get_replicability_assessment(self, assessment_id: str) -> ReplicabilityAssessmentRecord | None:
        with self._lock:
            return self._replicability_assessments.get(assessment_id)

    def get_latest_replicability_assessment(self) -> ReplicabilityAssessmentRecord | None:
        with self._lock:
            if self._latest_replicability_assessment_id is None:
                return None
            return self._replicability_assessments.get(self._latest_replicability_assessment_id)

    def save_design_draft(self, record: DesignDraftRecord) -> None:
        with self._lock:
            self._design_drafts[record.design_id] = record
            self._latest_design_draft_id = record.design_id

    def get_design_draft(self, design_id: str) -> DesignDraftRecord | None:
        with self._lock:
            return self._design_drafts.get(design_id)

    def get_latest_design_draft(self) -> DesignDraftRecord | None:
        with self._lock:
            if self._latest_design_draft_id is None:
                return None
            return self._design_drafts.get(self._latest_design_draft_id)

    def save_run(self, record: RunRecord) -> None:
        with self._lock:
            self._runs[record.run_id] = record
            self._latest_run_id = record.run_id

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def get_latest_run(self) -> RunRecord | None:
        with self._lock:
            if self._latest_run_id is None:
                return None
            return self._runs.get(self._latest_run_id)

    def save_schedule(self, record: ScheduledOperationRecord) -> None:
        with self._lock:
            self._schedules[record.schedule_id] = record

    def get_schedule(self, schedule_id: str) -> ScheduledOperationRecord | None:
        with self._lock:
            return self._schedules.get(schedule_id)

    def list_schedules(self, operation_type: str | None = None) -> list[ScheduledOperationRecord]:
        with self._lock:
            records = list(self._schedules.values())
        if operation_type is not None:
            records = [record for record in records if record.operation_type == operation_type]
        return sorted(records, key=lambda record: record.created_at)

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
