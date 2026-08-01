from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
import yaml

from .schemas import ExperimentMatrix, ResolvedEvaluationContract, RunRecord


class MethodologyRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid')

    requirement_id: str = Field(min_length=1)
    config_path: str = Field(min_length=1)
    mode: Literal['comparison', 'decision']
    minimum_distinct_values: int = Field(default=1, ge=1)
    maximum_distinct_values: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1)


class MatrixPreflightReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    passed: bool
    job_count: int
    checks: list[str] = Field(default_factory=list)
    comparisons: dict[str, list[str]] = Field(default_factory=dict)
    decisions: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


EVALUATOR_OWNED_LITERALS = {
    'evaluation.json',
    'integrity_pass',
    'rubric_score',
}
SCANNED_SOURCE_SUFFIXES = {
    '.js',
    '.py',
    '.r',
    '.sh',
    '.ts',
}


def _config_value(config: dict[str, Any], dotted_path: str) -> Any:
    value: Any = config
    for component in dotted_path.split('.'):
        if not isinstance(value, dict) or component not in value:
            raise KeyError(dotted_path)
        value = value[component]
    return value


def _distinct_strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(str(item) for item in values))


def _load_config(path: Path) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f'candidate config is not valid YAML: {exc}') from exc
    if not isinstance(parsed, dict):
        raise ValueError('candidate config must contain a YAML object')
    return parsed


def _dict_keys(
    expression: ast.expr,
    assignments: dict[str, ast.expr],
    subscript_keys: dict[str, set[str]],
    *,
    resolving: frozenset[str] = frozenset(),
) -> set[str]:
    if isinstance(expression, ast.Name):
        if expression.id in resolving:
            return set()
        assigned = assignments.get(expression.id)
        keys = set(subscript_keys.get(expression.id, set()))
        if assigned is not None:
            keys.update(
                _dict_keys(
                    assigned,
                    assignments,
                    subscript_keys,
                    resolving=resolving | {expression.id},
                )
            )
        return keys
    if not isinstance(expression, ast.Dict):
        return set()
    keys: set[str] = set()
    for key, value in zip(expression.keys, expression.values, strict=True):
        if key is None:
            keys.update(
                _dict_keys(
                    value,
                    assignments,
                    subscript_keys,
                    resolving=resolving,
                )
            )
        elif isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def _metrics_root_errors(
    tree: ast.AST,
    *,
    relative: str,
    required_metric_keys: list[str],
) -> list[str]:
    if not required_metric_keys:
        return []
    assignments: dict[str, ast.expr] = {}
    subscript_keys: dict[str, set[str]] = {}
    metric_handles: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                subscript_keys.setdefault(target.value.id, set()).add(
                    target.slice.value
                )
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            if (
                not isinstance(item.optional_vars, ast.Name)
                or not isinstance(item.context_expr, ast.Call)
                or not item.context_expr.args
            ):
                continue
            target_text = ast.unparse(item.context_expr.args[0])
            if 'metrics.json' in target_text:
                metric_handles.add(item.optional_vars.id)

    serialized_keys: set[str] = set()
    found_serialization = False
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr != 'dump'
            or len(node.args) < 2
            or not isinstance(node.args[1], ast.Name)
            or node.args[1].id not in metric_handles
        ):
            continue
        found_serialization = True
        serialized_keys.update(
            _dict_keys(node.args[0], assignments, subscript_keys)
        )
    if not found_serialization:
        return [
            f'{relative} does not have a statically verifiable JSON write to '
            'metrics.json'
        ]
    missing = sorted(set(required_metric_keys) - serialized_keys)
    if not missing:
        return []
    return [
        f'{relative} serializes metrics.json without required root key(s): '
        + ', '.join(missing)
    ]


def _source_errors(
    source: Path,
    *,
    required_metric_keys: list[str],
) -> list[str]:
    errors: list[str] = []
    if not source.is_dir():
        return ['imported task source directory is missing']
    for path in sorted(source.rglob('*')):
        if (
            not path.is_file()
            or path.is_symlink()
            or path.suffix.lower() not in SCANNED_SOURCE_SUFFIXES
        ):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            errors.append(f'source file is not UTF-8 text: {path.name}')
            continue
        relative = path.relative_to(source).as_posix()
        if path.suffix.lower() == '.py':
            try:
                tree = ast.parse(text, filename=relative)
            except SyntaxError as exc:
                errors.append(
                    f'Python syntax check failed for {relative}:{exc.lineno}: '
                    f'{exc.msg}'
                )
            else:
                if path.name == 'run.py':
                    errors.extend(
                        _metrics_root_errors(
                            tree,
                            relative=relative,
                            required_metric_keys=required_metric_keys,
                        )
                    )
        reserved = sorted(
            literal for literal in EVALUATOR_OWNED_LITERALS if literal in text
        )
        if reserved:
            errors.append(
                f'{relative} references evaluator-owned output '
                f'{", ".join(reserved)}; workloads emit evidence and metrics, '
                'while the immutable contract owns evaluation.json, '
                'integrity_pass, and rubric_score'
            )
    return errors


def preflight_matrix(
    *,
    run: RunRecord,
    matrix: ExperimentMatrix,
    contract: ResolvedEvaluationContract,
) -> MatrixPreflightReport:
    workspace = Path(run.beaker_workspace).resolve()
    base_config = (workspace / matrix.base_config).resolve()
    errors: list[str] = []
    checks: list[str] = []
    comparisons: dict[str, list[str]] = {}
    decisions: dict[str, list[str]] = {}

    if not base_config.is_relative_to(workspace) or not base_config.is_file():
        errors.append(
            'base_config does not exist inside the Beaker workspace: '
            f'{matrix.base_config}'
        )
        config: dict[str, Any] = {}
    else:
        try:
            config = _load_config(base_config)
            checks.append(f'candidate config parsed: {matrix.base_config}')
        except ValueError as exc:
            config = {}
            errors.append(str(exc))

    raw_requirements = contract.descriptor.manifest.get(
        'methodology_requirements',
        [],
    )
    try:
        requirements = [
            MethodologyRequirement.model_validate(item)
            for item in raw_requirements
        ]
    except ValueError as exc:
        errors.append(f'evaluation contract methodology requirements are invalid: {exc}')
        requirements = []

    for requirement in requirements:
        try:
            configured_value = _config_value(config, requirement.config_path)
        except KeyError:
            errors.append(
                f'missing methodology setting `{requirement.config_path}`: '
                f'{requirement.description}'
            )
            continue
        if isinstance(configured_value, dict):
            errors.append(
                f'`{requirement.config_path}` must directly contain a scalar '
                'or list of values, not a metadata object; do not wrap values '
                'beneath `description` or `values`'
            )
            continue
        values = _distinct_strings(configured_value)
        count = len(values)
        if count < requirement.minimum_distinct_values:
            errors.append(
                f'`{requirement.config_path}` requires at least '
                f'{requirement.minimum_distinct_values} distinct value(s); '
                f'found {count}'
            )
        if (
            requirement.maximum_distinct_values is not None
            and count > requirement.maximum_distinct_values
        ):
            errors.append(
                f'`{requirement.config_path}` allows at most '
                f'{requirement.maximum_distinct_values} distinct value(s); '
                f'found {count}'
            )
        target = comparisons if requirement.mode == 'comparison' else decisions
        target[requirement.requirement_id] = values

    if requirements:
        checks.append(
            f'validated {len(requirements)} contract methodology requirement(s)'
        )

    if run.task_definition:
        source = (
            workspace / str(run.task_definition['source_subdirectory'])
        ).resolve()
        if not source.is_relative_to(workspace):
            errors.append('imported task source directory escapes the workspace')
        else:
            source_findings = _source_errors(
                source,
                required_metric_keys=list(
                    contract.descriptor.manifest.get(
                        'required_metric_keys',
                        [],
                    )
                ),
            )
            errors.extend(source_findings)
            if not source_findings:
                checks.append(
                    'workspace syntax and evaluator-output ownership checks passed'
                )

    job_count = len(matrix.variants) * len(matrix.seeds)
    checks.append(f'deterministic expansion produces {job_count} job(s)')
    return MatrixPreflightReport(
        passed=not errors,
        job_count=job_count,
        checks=checks,
        comparisons=comparisons,
        decisions=decisions,
        errors=errors,
    )
