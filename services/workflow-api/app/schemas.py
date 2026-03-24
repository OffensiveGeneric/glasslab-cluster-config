from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.common.schemas import ArtifactsIndex, RunManifest, RunStatus


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str = Field(min_length=3)
    objective: str = Field(min_length=5)
    inputs: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(min_length=1)
    resource_profile: str | None = None
    submitted_by: str | None = None
    trace_id: str | None = None

    @field_validator('models')
    @classmethod
    def validate_unique_models(cls, value: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(value))
        if len(deduped) != len(value):
            raise ValueError('models must be unique')
        return value


class IntakeCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    raw_request: str = Field(min_length=10)
    source_refs: list[str] = Field(default_factory=list)
    source_type: str | None = None
    notes: list[str] = Field(default_factory=list)
    submitted_by: str | None = None
    trace_id: str | None = None

    @field_validator('source_refs', 'notes')
    @classmethod
    def validate_non_empty_unique_strings(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('list entries must be unique')
        return deduped


class IntakeRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    source_type: str
    source_refs: list[str] = Field(default_factory=list)
    raw_request: str
    normalized_summary: str
    workflow_family_candidates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    submitted_by: str


class InterpretationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    interpretation_id: str
    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    source_type: str
    normalized_summary: str
    extracted_method_summary: str
    candidate_workflow_families: list[str] = Field(default_factory=list)
    dataset_hints: list[str] = Field(default_factory=list)
    evaluation_targets: list[str] = Field(default_factory=list)
    extracted_claims: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    submitted_by: str


class ReplicabilityAssessmentRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    assessment_id: str
    interpretation_id: str
    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    recommendation: str
    recommended_workflow_id: str | None = None
    candidate_workflow_families: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    approval_tier: str | None = None
    assessment_notes: list[str] = Field(default_factory=list)
    submitted_by: str


class DesignDraftRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    design_id: str
    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    workflow_id: str
    workflow_family: str
    objective: str
    declared_inputs: dict[str, Any] = Field(default_factory=dict)
    unresolved_inputs: list[str] = Field(default_factory=list)
    candidate_models: list[str] = Field(default_factory=list)
    resource_profile: str
    expected_artifacts: dict[str, list[str]]
    approval_tier: str
    design_notes: list[str] = Field(default_factory=list)
    submitted_by: str


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    field: str
    message: str


class JobSubmissionReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_name: str
    namespace: str
    accepted_at: datetime
    status: str
    detail: str


class WorkflowFamilySummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str
    display_name: str
    workflow_family: str
    description: str
    allowed_models: list[str]
    resource_profile: str
    approval_tier: str


class RunRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    workflow_id: str
    created_at: datetime
    updated_at: datetime
    manifest: RunManifest
    status: RunStatus
    job_submission: JobSubmissionReceipt
    source_design_id: str | None = None
    source_intake_id: str | None = None
    run_purpose: str | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)


class LogEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    timestamp: datetime
    level: str
    message: str
    payload: dict[str, Any] | None = None


class RunArtifactsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    artifacts: ArtifactsIndex


class RunLogsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    logs: list[LogEntry]
