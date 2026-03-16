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
