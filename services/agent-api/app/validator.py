from __future__ import annotations

from pydantic import ValidationError

from .registry import (
    ALLOWED_SPEC_KEYS,
    COMPARE_TO_OPTIONS,
    DATASET_REGISTRY,
    FEATURE_PROFILE_REGISTRY,
    MODEL_REGISTRY,
    PIPELINE_REGISTRY,
    RESOURCE_PROFILE_REGISTRY,
)
from .schemas import PlannerSpec, ValidationResult


def validate_spec(spec: PlannerSpec | dict) -> ValidationResult:
    payload = spec.model_dump(mode='json') if isinstance(spec, PlannerSpec) else dict(spec)
    errors: list[str] = []

    unknown_fields = sorted(set(payload) - ALLOWED_SPEC_KEYS)
    if unknown_fields:
        errors.append(f'unknown fields: {", ".join(unknown_fields)}')

    missing_fields = sorted(ALLOWED_SPEC_KEYS - set(payload))
    if missing_fields:
        errors.append(f'missing required fields: {", ".join(missing_fields)}')

    try:
        normalized = PlannerSpec.model_validate(payload)
    except ValidationError as exc:
        errors.extend(_format_validation_errors(exc))
        return ValidationResult(valid=False, errors=_dedupe(errors))

    pipeline = PIPELINE_REGISTRY.get(normalized.pipeline)
    if pipeline is None:
        errors.append(f'unsupported pipeline: {normalized.pipeline}')
    dataset = DATASET_REGISTRY.get(normalized.dataset)
    if dataset is None:
        errors.append(f'unsupported dataset: {normalized.dataset}')

    invalid_models = [model_name for model_name in normalized.models if model_name not in MODEL_REGISTRY]
    if invalid_models:
        errors.append(f'unsupported model names: {", ".join(sorted(invalid_models))}')
    elif pipeline is not None:
        disallowed_models = [
            model_name
            for model_name in normalized.models
            if model_name not in pipeline['supported_models']
        ]
        if disallowed_models:
            errors.append(
                f'models not allowed for {normalized.pipeline}: {", ".join(sorted(disallowed_models))}'
            )

    if normalized.feature_profile not in FEATURE_PROFILE_REGISTRY:
        errors.append(f'unsupported feature profile: {normalized.feature_profile}')
    if normalized.resource_profile not in RESOURCE_PROFILE_REGISTRY:
        errors.append(f'unsupported resource profile: {normalized.resource_profile}')
    if normalized.compare_to not in COMPARE_TO_OPTIONS:
        errors.append(f'unsupported compare_to value: {normalized.compare_to}')

    if normalized.resource_profile == 'gpu-small':
        gpu_capable_models = [
            model_name for model_name in normalized.models if MODEL_REGISTRY[model_name]['supports_gpu']
        ]
        if not gpu_capable_models:
            errors.append('gpu-small requires at least one GPU-capable model selection')

    return ValidationResult(valid=not errors, errors=_dedupe(errors))


def _format_validation_errors(exc: ValidationError) -> list[str]:
    formatted: list[str] = []
    for error in exc.errors():
        location = '.'.join(str(part) for part in error['loc'])
        formatted.append(f'{location}: {error["msg"]}')
    return formatted


def _dedupe(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))
