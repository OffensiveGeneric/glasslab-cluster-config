from __future__ import annotations

from services.common.schemas import WorkflowRegistryEntry

from .schemas import RunCreateRequest, ValidationIssue


def validate_run_request(request: RunCreateRequest, workflow: WorkflowRegistryEntry) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    allowed_inputs = {item.name for item in workflow.required_inputs}
    required_inputs = {item.name for item in workflow.required_inputs if item.required}
    provided_inputs = set(request.inputs.keys())

    missing_inputs = sorted(required_inputs - provided_inputs)
    for name in missing_inputs:
        issues.append(ValidationIssue(field=f'inputs.{name}', message='required input is missing'))

    unknown_inputs = sorted(provided_inputs - allowed_inputs)
    for name in unknown_inputs:
        issues.append(ValidationIssue(field=f'inputs.{name}', message='input is not declared in the workflow registry'))

    disallowed_models = [model for model in request.models if model not in workflow.allowed_models]
    if disallowed_models:
        issues.append(
            ValidationIssue(
                field='models',
                message=f'disallowed models requested: {", ".join(disallowed_models)}',
            )
        )

    if request.resource_profile and request.resource_profile != workflow.resource_profile.profile_name:
        issues.append(
            ValidationIssue(
                field='resource_profile',
                message=f'workflow requires resource profile {workflow.resource_profile.profile_name}',
            )
        )

    return issues
