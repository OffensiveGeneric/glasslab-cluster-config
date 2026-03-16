from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RunState = Literal['accepted', 'queued', 'running', 'succeeded', 'failed', 'rejected']
MetricDirection = Literal['maximize', 'minimize']


class RunManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    workflow_id: str
    workflow_family: str
    display_name: str
    objective: str = Field(min_length=5)
    submitted_by: str
    submitted_at: datetime
    inputs: dict[str, Any] = Field(default_factory=dict)
    requested_models: list[str] = Field(min_length=1)
    resource_profile: str
    runner_image: str
    evaluator_type: str
    approval_tier: str
    expected_artifacts: dict[str, list[str]]

    @field_validator('requested_models')
    @classmethod
    def validate_unique_models(cls, value: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(value))
        if len(deduped) != len(value):
            raise ValueError('requested_models must be unique')
        return value


class RunStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    status: RunState
    updated_at: datetime
    detail: str | None = None


class MetricRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    value: float
    direction: MetricDirection
    split: str | None = None


class Metrics(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    primary_metric: str | None = None
    values: list[MetricRecord] = Field(default_factory=list)
    runtime_seconds: float | None = None
    notes: list[str] = Field(default_factory=list)


class ArtifactIndexEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    path: str
    media_type: str
    required: bool = True
    size_bytes: int | None = None
    description: str | None = None


class ArtifactsIndex(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    artifacts: list[ArtifactIndexEntry] = Field(default_factory=list)
