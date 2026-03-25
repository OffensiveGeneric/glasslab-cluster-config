from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntakePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    intake_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    raw_request: str = Field(min_length=1)
    normalized_summary: str = Field(min_length=1)
    document_refs: list[str] = Field(default_factory=list)
    workflow_family_candidates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    submitted_by: str = Field(min_length=1)

    @field_validator('source_refs', 'document_refs', 'workflow_family_candidates', 'notes')
    @classmethod
    def validate_unique_non_empty_lists(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(cleaned) != len(deduped):
            raise ValueError('list entries must be unique')
        return deduped


class WorkflowPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str = Field(min_length=1)
    workflow_family: str = Field(min_length=1)
    allowed_models: list[str] = Field(default_factory=list)
    expected_artifacts: dict[str, list[str]]
    resource_profile_name: str = Field(min_length=1)
    approval_tier: str = Field(min_length=1)


class DesignDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')

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


class ModelBackendMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    provider: str
    base_url: str | None = None
    model: str
    timeout_seconds: float


class DesignRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str = Field(min_length=1)
    intake: IntakePayload
    workflow: WorkflowPayload


class DesignResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str
    draft: DesignDraft
    model_backend: ModelBackendMetadata
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: str
    model_backend: dict[str, Any]
