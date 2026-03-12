from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AllowedModel = Literal['logistic_regression', 'random_forest', 'xgboost_optional']
AllowedFeatureProfile = Literal['basic', 'extended']
AllowedResourceProfile = Literal['cpu-small', 'cpu-medium', 'gpu-small']
AllowedCompareTo = Literal['none', 'latest_successful']


class PlannerSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    pipeline: Literal['titanic_baseline']
    dataset: Literal['titanic']
    models: list[AllowedModel]
    feature_profile: AllowedFeatureProfile
    resource_profile: AllowedResourceProfile
    compare_to: AllowedCompareTo
    produce_submission: bool

    @field_validator('models')
    @classmethod
    def validate_models(cls, value: list[AllowedModel]) -> list[AllowedModel]:
        if not value:
            raise ValueError('models must not be empty')
        if len(set(value)) != len(value):
            raise ValueError('models must be unique')
        return value


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    spec: PlannerSpec
    source: str
    raw_output: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExperimentCreateRequest(BaseModel):
    request_text: str = Field(min_length=5)
    trace_id: str | None = None


class ArtifactRef(BaseModel):
    name: str
    path: str
    size_bytes: int | None = None


class ExperimentLogEntry(BaseModel):
    timestamp: datetime
    level: str
    message: str
    payload: dict[str, Any] | None = None


class ExperimentRecord(BaseModel):
    id: str
    trace_id: str
    request_text: str
    status: str
    planner_source: str | None = None
    planner_raw_output: str | None = None
    normalized_spec: PlannerSpec | None = None
    validation: ValidationResult | None = None
    job_name: str | None = None
    result_summary: str | None = None
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    error_message: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ExperimentArtifactsResponse(BaseModel):
    experiment_id: str
    artifacts: list[ArtifactRef]


class ExperimentLogsResponse(BaseModel):
    experiment_id: str
    logs: list[ExperimentLogEntry]
