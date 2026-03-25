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
    workflow_family_candidates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    submitted_by: str = Field(min_length=1)

    @field_validator('source_refs', 'workflow_family_candidates', 'notes')
    @classmethod
    def validate_unique_non_empty_lists(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(cleaned) != len(deduped):
            raise ValueError('list entries must be unique')
        return deduped


class InterpretationDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')

    source_type: str
    normalized_summary: str
    extracted_method_summary: str
    candidate_workflow_families: list[str] = Field(default_factory=list)
    dataset_hints: list[str] = Field(default_factory=list)
    evaluation_targets: list[str] = Field(default_factory=list)
    extracted_claims: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class ModelBackendMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    provider: str
    base_url: str | None = None
    model: str
    timeout_seconds: float


class InterpretationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str = Field(min_length=1)
    intake: IntakePayload


class InterpretationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str
    draft: InterpretationDraft
    model_backend: ModelBackendMetadata
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: str
    model_backend: dict[str, Any]
