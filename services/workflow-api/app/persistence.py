from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock

from services.common.schemas import ArtifactsIndex

from .schemas import (
    DesignDraftRecord,
    IntakeRecord,
    InterpretationRecord,
    LogEntry,
    PaperIntakeQueueRecord,
    ResearchSessionRecord,
    ResearchProblemRecord,
    ReplicabilityAssessmentRecord,
    RunRecord,
    ScheduledExecutionRecord,
    ScheduledOperationRecord,
    SourceDocumentRecord,
)


class RunStore(ABC):
    @abstractmethod
    def save_research_session(self, record: ResearchSessionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_research_session(self, session_id: str) -> ResearchSessionRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_research_session(self) -> ResearchSessionRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_research_sessions(self) -> list[ResearchSessionRecord]:
        raise NotImplementedError

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
    def save_research_problem(self, record: ResearchProblemRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_research_problem(self, problem_id: str) -> ResearchProblemRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_research_problem(self) -> ResearchProblemRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_paper_intake_queue(self, record: PaperIntakeQueueRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_paper_intake_queue(self, queue_id: str) -> PaperIntakeQueueRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_paper_intake_queue(self) -> PaperIntakeQueueRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_paper_intake_queues(self) -> list[PaperIntakeQueueRecord]:
        raise NotImplementedError

    @abstractmethod
    def save_source_document(self, record: SourceDocumentRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_source_document(self, document_id: str) -> SourceDocumentRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_source_document(self) -> SourceDocumentRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_source_documents(self) -> list[SourceDocumentRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> RunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_run(self) -> RunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_runs(self) -> list[RunRecord]:
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
    def save_execution(self, record: ScheduledExecutionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_executions(self, schedule_id: str | None = None) -> list[ScheduledExecutionRecord]:
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
        self._research_sessions: dict[str, ResearchSessionRecord] = {}
        self._latest_research_session_id: str | None = None
        self._intakes: dict[str, IntakeRecord] = {}
        self._latest_intake_id: str | None = None
        self._interpretations: dict[str, InterpretationRecord] = {}
        self._latest_interpretation_id: str | None = None
        self._replicability_assessments: dict[str, ReplicabilityAssessmentRecord] = {}
        self._latest_replicability_assessment_id: str | None = None
        self._design_drafts: dict[str, DesignDraftRecord] = {}
        self._latest_design_draft_id: str | None = None
        self._research_problems: dict[str, ResearchProblemRecord] = {}
        self._latest_research_problem_id: str | None = None
        self._paper_intake_queues: dict[str, PaperIntakeQueueRecord] = {}
        self._latest_paper_intake_queue_id: str | None = None
        self._source_documents: dict[str, SourceDocumentRecord] = {}
        self._latest_source_document_id: str | None = None
        self._runs: dict[str, RunRecord] = {}
        self._latest_run_id: str | None = None
        self._schedules: dict[str, ScheduledOperationRecord] = {}
        self._executions: dict[str, ScheduledExecutionRecord] = {}
        self._artifacts: dict[str, ArtifactsIndex] = {}
        self._logs: dict[str, list[LogEntry]] = {}
        self._lock = Lock()

    def save_research_session(self, record: ResearchSessionRecord) -> None:
        with self._lock:
            self._research_sessions[record.session_id] = record
            self._latest_research_session_id = record.session_id

    def get_research_session(self, session_id: str) -> ResearchSessionRecord | None:
        with self._lock:
            return self._research_sessions.get(session_id)

    def get_latest_research_session(self) -> ResearchSessionRecord | None:
        with self._lock:
            if self._latest_research_session_id is None:
                return None
            return self._research_sessions.get(self._latest_research_session_id)

    def list_research_sessions(self) -> list[ResearchSessionRecord]:
        with self._lock:
            records = list(self._research_sessions.values())
        return sorted(records, key=lambda record: record.created_at)

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

    def save_research_problem(self, record: ResearchProblemRecord) -> None:
        with self._lock:
            self._research_problems[record.problem_id] = record
            self._latest_research_problem_id = record.problem_id

    def get_research_problem(self, problem_id: str) -> ResearchProblemRecord | None:
        with self._lock:
            return self._research_problems.get(problem_id)

    def get_latest_research_problem(self) -> ResearchProblemRecord | None:
        with self._lock:
            if self._latest_research_problem_id is None:
                return None
            return self._research_problems.get(self._latest_research_problem_id)

    def save_paper_intake_queue(self, record: PaperIntakeQueueRecord) -> None:
        with self._lock:
            self._paper_intake_queues[record.queue_id] = record
            self._latest_paper_intake_queue_id = record.queue_id

    def get_paper_intake_queue(self, queue_id: str) -> PaperIntakeQueueRecord | None:
        with self._lock:
            return self._paper_intake_queues.get(queue_id)

    def get_latest_paper_intake_queue(self) -> PaperIntakeQueueRecord | None:
        with self._lock:
            if self._latest_paper_intake_queue_id is None:
                return None
            return self._paper_intake_queues.get(self._latest_paper_intake_queue_id)

    def list_paper_intake_queues(self) -> list[PaperIntakeQueueRecord]:
        with self._lock:
            records = list(self._paper_intake_queues.values())
        return sorted(records, key=lambda record: record.created_at)

    def save_source_document(self, record: SourceDocumentRecord) -> None:
        with self._lock:
            self._source_documents[record.document_id] = record
            self._latest_source_document_id = record.document_id

    def get_source_document(self, document_id: str) -> SourceDocumentRecord | None:
        with self._lock:
            return self._source_documents.get(document_id)

    def get_latest_source_document(self) -> SourceDocumentRecord | None:
        with self._lock:
            if self._latest_source_document_id is None:
                return None
            return self._source_documents.get(self._latest_source_document_id)

    def list_source_documents(self) -> list[SourceDocumentRecord]:
        with self._lock:
            records = list(self._source_documents.values())
        return sorted(records, key=lambda record: record.created_at)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def get_latest_run(self) -> RunRecord | None:
        with self._lock:
            if self._latest_run_id is None:
                return None
            return self._runs.get(self._latest_run_id)

    def list_runs(self) -> list[RunRecord]:
        with self._lock:
            records = list(self._runs.values())
        return sorted(records, key=lambda record: record.created_at)

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

    def save_execution(self, record: ScheduledExecutionRecord) -> None:
        with self._lock:
            self._executions[record.execution_id] = record

    def list_executions(self, schedule_id: str | None = None) -> list[ScheduledExecutionRecord]:
        with self._lock:
            records = list(self._executions.values())
        if schedule_id is not None:
            records = [record for record in records if record.schedule_id == schedule_id]
        return sorted(records, key=lambda record: record.started_at)

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
