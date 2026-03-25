from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InterpretationPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    interpretation_id: str = Field(min_length=1)
    intake_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    normalized_summary: str = Field(min_length=1)
    extracted_method_summary: str = Field(min_length=1)
    literature_state_summary: str = Field(min_length=1)
    candidate_workflow_families: list[str] = Field(default_factory=list)
    dataset_hints: list[str] = Field(default_factory=list)
    evaluation_targets: list[str] = Field(default_factory=list)
    extracted_claims: list[str] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)
    bounded_experiment_ideas: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    submitted_by: str = Field(min_length=1)

    @field_validator(
        'candidate_workflow_families',
        'dataset_hints',
        'evaluation_targets',
        'extracted_claims',
        'research_gaps',
        'bounded_experiment_ideas',
        'unresolved_questions',
    )
    @classmethod
    def validate_unique_non_empty_lists(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(cleaned) != len(deduped):
            raise ValueError('list entries must be unique')
        return deduped


class WorkflowCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str = Field(min_length=1)
    approval_tier: str = Field(min_length=1)


class AssessmentDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')

    recommendation: str
    recommended_workflow_id: str | None = None
    candidate_workflow_families: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    approval_tier: str | None = None
    assessment_notes: list[str] = Field(default_factory=list)
    status: str


class ModelBackendMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')

    provider: str
    base_url: str | None = None
    model: str
    timeout_seconds: float


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str = Field(min_length=1)
    interpretation: InterpretationPayload
    available_workflows: list[WorkflowCandidate] = Field(default_factory=list)


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str
    draft: AssessmentDraft
    model_backend: ModelBackendMetadata
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: str
    model_backend: dict[str, Any]
