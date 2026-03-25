from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkerConfigMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_api_url: str
    timeout_seconds: float


class ScheduledExecutionPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    execution_id: str
    schedule_id: str
    operation_type: str
    result_status: str
    result_detail: str
    digest_payload: dict[str, Any] = Field(default_factory=dict)


class RunOnceResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    worker_status: str
    executed_count: int
    executions: list[ScheduledExecutionPayload] = Field(default_factory=list)
    worker_config: WorkerConfigMetadata


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: str
    worker_config: WorkerConfigMetadata
