from app.validator import validate_spec


VALID_SPEC = {
    'pipeline': 'titanic_baseline',
    'dataset': 'titanic',
    'models': ['logistic_regression', 'random_forest'],
    'feature_profile': 'basic',
    'resource_profile': 'cpu-small',
    'compare_to': 'none',
    'produce_submission': True,
}


def test_validate_spec_accepts_registry_values() -> None:
    result = validate_spec(VALID_SPEC)

    assert result.valid is True
    assert result.errors == []


def test_validate_spec_rejects_unknown_fields() -> None:
    result = validate_spec({**VALID_SPEC, 'unknown_flag': True})

    assert result.valid is False
    assert any('unknown fields' in error for error in result.errors)


def test_validate_spec_rejects_gpu_profile_for_cpu_only_models() -> None:
    result = validate_spec({**VALID_SPEC, 'resource_profile': 'gpu-small'})

    assert result.valid is False
    assert any('gpu-small requires at least one GPU-capable model selection' in error for error in result.errors)
