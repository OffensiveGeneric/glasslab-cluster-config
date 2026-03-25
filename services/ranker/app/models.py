from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RankCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowFamilyRankRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    candidates: list[RankCandidate] = Field(min_length=1)
    hints: dict[str, Any] = Field(default_factory=dict)


class RankedCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str
    score: float
    reason: str


class WorkflowFamilyRankResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str
    ranked_candidates: list[RankedCandidate]
    ranking_basis: str
