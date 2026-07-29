from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunState(StrEnum):
    CREATED = 'CREATED'
    PREPARING = 'PREPARING'
    HONEYDEW_DRAFTING_PROTOCOL = 'HONEYDEW_DRAFTING_PROTOCOL'
    AWAITING_PROTOCOL_APPROVAL = 'AWAITING_PROTOCOL_APPROVAL'
    BEAKER_IMPLEMENTING = 'BEAKER_IMPLEMENTING'
    HONEYDEW_REVIEWING = 'HONEYDEW_REVIEWING'
    BEAKER_REVISING = 'BEAKER_REVISING'
    AWAITING_EXECUTION_APPROVAL = 'AWAITING_EXECUTION_APPROVAL'
    JOB_QUEUED = 'JOB_QUEUED'
    JOB_RUNNING = 'JOB_RUNNING'
    BEAKER_ANALYZING = 'BEAKER_ANALYZING'
    HONEYDEW_VERIFYING = 'HONEYDEW_VERIFYING'
    HONEYDEW_WRITING_REPORT = 'HONEYDEW_WRITING_REPORT'
    AWAITING_FINAL_ACCEPTANCE = 'AWAITING_FINAL_ACCEPTANCE'
    COMPLETE = 'COMPLETE'
    PAUSED = 'PAUSED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    TIMED_OUT = 'TIMED_OUT'


TERMINAL_STATES = {
    RunState.COMPLETE,
    RunState.FAILED,
    RunState.CANCELLED,
    RunState.TIMED_OUT,
}


class AgentName(StrEnum):
    HONEYDEW = 'honeydew'
    BEAKER = 'beaker'
    ORCHESTRATOR = 'orchestrator'


class TurnKind(StrEnum):
    PROTOCOL_DRAFT = 'protocol_draft'
    IMPLEMENTATION_PROPOSAL = 'implementation_proposal'
    METHODOLOGY_REVIEW = 'methodology_review'
    REVISION = 'revision'
    EXPERIMENT_ANALYSIS = 'experiment_analysis'
    VERIFICATION = 'verification'
    FINAL_REPORT = 'final_report'


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')

    text: str = Field(min_length=1)
    evidence: list[
        Annotated[
            str,
            Field(
                pattern=r'^(artifact|git|event|job|contract)://.+$',
            ),
        ]
    ] = Field(default_factory=list)

    @field_validator('evidence')
    @classmethod
    def validate_evidence_uris(cls, value: list[str]) -> list[str]:
        allowed = ('artifact://', 'git://', 'event://', 'job://', 'contract://')
        for uri in value:
            if not uri.startswith(allowed):
                raise ValueError(f'unsupported evidence URI: {uri}')
        return list(dict.fromkeys(value))


class RequestedAction(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)


class ProducedFile(BaseModel):
    model_config = ConfigDict(extra='forbid')

    path: str = Field(
        min_length=1,
        pattern=(
            r'^[A-Za-z0-9_-][A-Za-z0-9._-]*'
            r'(?:/[A-Za-z0-9_-][A-Za-z0-9._-]*)*$'
        ),
    )
    purpose: Literal['protocol', 'implementation', 'analysis', 'report', 'other']

    @field_validator('path')
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.strip().replace('\\', '/')
        parts = normalized.split('/')
        if (
            not normalized
            or normalized.startswith('/')
            or '..' in parts
            or any(not part for part in parts)
        ):
            raise ValueError('produced file must be a safe relative path')
        return normalized


class AgentTurnResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: TurnKind
    summary: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    requested_actions: list[RequestedAction] = Field(default_factory=list)
    produced_files: list[ProducedFile] = Field(default_factory=list)
    message_to_other_agent: str = ''
    recommended_next_state: RunState | None = None
    done: bool = False


class ResourceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    cpu: float = Field(default=1.0, gt=0)
    memory_gib: float = Field(default=2.0, gt=0)
    gpus: int = Field(default=0, ge=0)
    wallclock_minutes: int = Field(default=30, ge=1)


class ExperimentVariant(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,62}$')
    overrides: dict[str, Any] = Field(default_factory=dict)


class ExperimentMatrix(BaseModel):
    model_config = ConfigDict(extra='forbid')

    base_config: str = Field(min_length=1)
    variants: list[ExperimentVariant] = Field(min_length=1)
    seeds: list[int] = Field(min_length=1)
    maximum_parallel_jobs: int = Field(default=1, ge=1)
    runner_image: str = Field(min_length=1)
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    required_artifacts: list[str] = Field(default_factory=list)

    @field_validator('base_config')
    @classmethod
    def safe_base_config(cls, value: str) -> str:
        normalized = value.strip().replace('\\', '/')
        parts = normalized.split('/')
        if (
            not normalized
            or normalized.startswith('/')
            or '..' in parts
            or any(not part for part in parts)
        ):
            raise ValueError('base_config must be a safe relative path')
        return normalized

    @field_validator('seeds')
    @classmethod
    def unique_seeds(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError('seeds must be unique')
        return value

    @field_validator('variants')
    @classmethod
    def unique_variants(
        cls,
        value: list[ExperimentVariant],
    ) -> list[ExperimentVariant]:
        names = [item.name for item in value]
        if len(names) != len(set(names)):
            raise ValueError('variant names must be unique')
        return value


class EvaluationContractDescriptor(BaseModel):
    model_config = ConfigDict(extra='forbid')

    contract_id: str = Field(min_length=3)
    version: str = Field(min_length=1)
    manifest: dict[str, Any]
    execution_wrapper: str = Field(min_length=1)
    evaluation_entry_point: str = Field(min_length=1)
    expected_input_schema: str = Field(min_length=1)
    expected_output_schema: str = Field(min_length=1)
    required_artifacts: list[str] = Field(min_length=1)
    resource_constraints: ResourceRequest
    container_image_digest: str | None = None


class ResolvedEvaluationContract(BaseModel):
    model_config = ConfigDict(extra='forbid')

    descriptor: EvaluationContractDescriptor
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    root_path: str


class ExpandedJobSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    orchestrator_job_id: str
    run_id: str
    action_id: str
    variant_name: str
    seed: int
    idempotency_key: str
    base_config: str
    overrides: dict[str, Any]
    runner_image: str
    resources: ResourceRequest
    required_artifacts: list[str]
    evaluation_contract_id: str
    evaluation_contract_version: str
    evaluation_contract_digest: str


class RunRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    objective: str
    state: RunState
    protocol_path: str | None = None
    protocol_version: int = 0
    evaluation_contract_id: str
    evaluation_contract_version: str
    evaluation_contract_digest: str
    beaker_runtime_id: str | None = None
    beaker_session_id: str | None = None
    honeydew_runtime_id: str | None = None
    honeydew_session_id: str | None = None
    beaker_workspace: str
    honeydew_workspace: str
    shared_artifacts_path: str
    reports_path: str
    current_agent: AgentName | None = None
    turn_number: int = 0
    discord_thread_id: str | None = None
    discord_status_message_id: str | None = None
    maximum_turns: int
    maximum_runtime_seconds: int
    maximum_parallel_jobs: int
    resume_state: RunState | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime


class TurnRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    turn_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    agent: AgentName
    opencode_session_id: str | None = None
    opencode_message_id: str | None = None
    input_event: dict[str, Any] = Field(default_factory=dict)
    structured_output: AgentTurnResult | None = None
    status: Literal['running', 'completed', 'failed', 'aborted']
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PolicyClassification(StrEnum):
    AUTOMATIC = 'automatic'
    HONEYDEW_APPROVAL = 'honeydew_approval'
    HUMAN_APPROVAL = 'human_approval'
    HONEYDEW_AND_HUMAN_APPROVAL = 'honeydew_and_human_approval'
    DENY = 'deny'


class ApprovalStatus(StrEnum):
    AUTOMATICALLY_APPROVED = 'automatically_approved'
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    DENIED = 'denied'
    EXECUTION_FAILED = 'execution_failed'


class ActionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    action_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    proposed_by: AgentName
    type: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    policy_classification: PolicyClassification
    approval_status: ApprovalStatus
    honeydew_approved: bool = False
    honeydew_review_turn_id: str | None = None
    reviewer: str | None = None
    reason: str
    idempotency_key: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class JobStatus(StrEnum):
    QUEUED = 'queued'
    SUBMITTING = 'submitting'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    UNKNOWN = 'unknown'


JOB_TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


class JobRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_id: str
    run_id: str
    action_id: str
    kubernetes_namespace: str
    job_name: str | None = None
    kubernetes_uid: str | None = None
    external_run_id: str | None = None
    status: JobStatus
    requested_resources: ResourceRequest
    evaluation_contract_id: str
    evaluation_contract_version: str
    evaluation_contract_digest: str
    idempotency_key: str
    variant_name: str
    seed: int
    spec: ExpandedJobSpec
    exit_information: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    artifact_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    job_id: str | None = None
    type: str
    uri: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class EventRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    sequence_number: int
    run_id: str
    source: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    objective: str = Field(min_length=10)
    evaluation_contract_id: str | None = None
    evaluation_contract_version: str | None = None
    maximum_turns: int | None = Field(default=None, ge=1)
    maximum_runtime_seconds: int | None = Field(default=None, ge=60)
    maximum_parallel_jobs: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def require_contract_pair(self) -> 'RunCreateRequest':
        if bool(self.evaluation_contract_id) != bool(self.evaluation_contract_version):
            raise ValueError('evaluation contract ID and version must be supplied together')
        return self


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reviewer: str = Field(min_length=1)
    reason: str = Field(default='Approved by human reviewer.', min_length=1)


class RejectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class RunListResponse(BaseModel):
    runs: list[RunRecord]


class EventListResponse(BaseModel):
    events: list[EventRecord]


class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactRecord]
