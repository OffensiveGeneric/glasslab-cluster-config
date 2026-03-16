from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ComparedRun(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    workflow_id: str
    workflow_family: str
    models: list[str] = Field(default_factory=list)
    status: str
    primary_metric_name: str | None = None
    primary_metric_value: float | None = None
    primary_metric_direction: str | None = None
    runtime_seconds: float | None = None


class RankedRun(BaseModel):
    model_config = ConfigDict(extra='forbid')

    position: int
    run_id: str
    reason: str


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    compared_runs: list[ComparedRun] = Field(default_factory=list)
    ranking: list[RankedRun] = Field(default_factory=list)
    best_run_id: str | None = None
    comparison_basis: str
