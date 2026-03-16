from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ApprovalTier = Literal['tier-1-read-only', 'tier-2-approved-execution', 'tier-3-human-approval']
InputType = Literal['dataset', 'paper_bundle', 'artifact_bundle', 'notes', 'text', 'url', 'parameter_set']


class WorkflowInputSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str = Field(min_length=2)
    input_type: InputType
    required: bool = True
    description: str = Field(min_length=8)


class ExpectedArtifactsSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    required: list[str] = Field(min_length=1)
    optional: list[str] = Field(default_factory=list)

    @field_validator('required', 'optional')
    @classmethod
    def validate_unique_artifacts(cls, value: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(value))
        if len(deduped) != len(value):
            raise ValueError('artifact names must be unique')
        return value


class ResourceProfileSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    profile_name: str = Field(min_length=2)
    requests: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, str] = Field(default_factory=dict)
    node_selector: dict[str, str] = Field(default_factory=dict)


class WorkflowRegistryEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str = Field(min_length=3)
    display_name: str = Field(min_length=3)
    workflow_family: str = Field(min_length=3)
    description: str = Field(min_length=12)
    required_inputs: list[WorkflowInputSpec] = Field(min_length=1)
    allowed_models: list[str] = Field(min_length=1)
    runner_image: str = Field(min_length=3)
    evaluator_type: str = Field(min_length=3)
    expected_artifacts: ExpectedArtifactsSpec
    resource_profile: ResourceProfileSpec
    approval_tier: ApprovalTier

    @field_validator('allowed_models')
    @classmethod
    def validate_unique_models(cls, value: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(value))
        if len(deduped) != len(value):
            raise ValueError('allowed_models must be unique')
        return value

    @field_validator('required_inputs')
    @classmethod
    def validate_unique_inputs(cls, value: list[WorkflowInputSpec]) -> list[WorkflowInputSpec]:
        names = [item.name for item in value]
        deduped = list(dict.fromkeys(names))
        if len(deduped) != len(names):
            raise ValueError('required_inputs names must be unique')
        return value
