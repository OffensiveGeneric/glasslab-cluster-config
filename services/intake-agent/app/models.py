from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntakeCreatePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    raw_request: str = Field(min_length=10)
    source_refs: list[str] = Field(default_factory=list)
    source_type: str | None = None
    notes: list[str] = Field(default_factory=list)
    submitted_by: str | None = None

    @field_validator('source_refs', 'notes')
    @classmethod
    def validate_unique_non_empty_lists(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(cleaned) != len(deduped):
            raise ValueError('list entries must be unique')
        return deduped


class NormalizedIntakeDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source_type: str
    source_refs: list[str] = Field(default_factory=list)
    raw_request: str
    normalized_summary: str
    workflow_family_candidates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    submitted_by: str


class ModelBackendMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    provider: str
    base_url: str | None = None
    model: str
    timeout_seconds: float


class ApprovedSourcesSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    manifest_name: str
    manifest_version: int
    venue_count: int
    paper_count: int
    track_query_count: int
    approved_hosts: list[str] = Field(default_factory=list)


class NormalizeIntakeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str = Field(min_length=1)
    intake: IntakeCreatePayload


class NormalizeIntakeResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str
    draft: NormalizedIntakeDraft
    model_backend: ModelBackendMetadata
    approved_sources: ApprovedSourcesSummary
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: str
    model_backend: dict[str, Any]
    approved_sources: ApprovedSourcesSummary
