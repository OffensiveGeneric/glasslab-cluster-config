from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath


GENERATED_ARTIFACTS = {
    'run_manifest.json',
    'config.json',
    'evaluation.json',
    'artifacts_index.json',
    'status.json',
    'logs/',
    'source.zip',
}


def safe_relative_path(value: str) -> Path | None:
    path = PurePosixPath(value.rstrip('/'))
    if path.is_absolute() or '..' in path.parts or path.as_posix() in {'', '.'}:
        return None
    return Path(path.as_posix())


def main() -> int:
    root = Path(os.environ['GLASSLAB_OUTPUT_DIR'])
    failures: list[str] = []
    try:
        metrics = json.loads((root / 'metrics.json').read_text())
    except Exception as exc:
        metrics = {}
        failures.append(f'metrics.json is unavailable or invalid: {exc}')
    try:
        config = json.loads(os.environ['GLASSLAB_GENERIC_CONFIG_JSON'])
        task_spec = config['task_spec']
        if not isinstance(task_spec, dict):
            raise TypeError('task_spec is not an object')
    except Exception as exc:
        task_spec = {}
        failures.append(f'compiled task_spec is unavailable or invalid: {exc}')

    required_metrics = set(task_spec.get('required_metric_keys', []))
    missing_metrics = sorted(required_metrics - set(metrics))
    if missing_metrics:
        failures.append('missing metrics: ' + ', '.join(missing_metrics))

    checked_artifacts = 0
    for artifact in task_spec.get('required_artifacts', []):
        if artifact in GENERATED_ARTIFACTS:
            continue
        relative = safe_relative_path(str(artifact))
        if relative is None:
            failures.append(f'unsafe required artifact path: {artifact}')
            continue
        checked_artifacts += 1
        if not (root / relative).exists():
            failures.append(f'missing required evidence: {artifact}')
    if not (root / 'report.md').is_file():
        failures.append('missing required evidence: report.md')

    checks = max(1, len(required_metrics) + checked_artifacts + 1)
    score = round(100 * max(0, checks - len(failures)) / checks, 2)
    result = {
        'rubric_score': 0.0 if failures else score,
        'integrity_pass': not failures,
        'failures': failures,
        'required_metric_keys': sorted(required_metrics),
        'checked_task_artifacts': checked_artifacts,
        'contract_id': os.environ['GLASSLAB_EVALUATION_CONTRACT_ID'],
        'contract_version': os.environ['GLASSLAB_EVALUATION_CONTRACT_VERSION'],
        'contract_digest': os.environ['GLASSLAB_EVALUATION_CONTRACT_DIGEST'],
    }
    (root / 'evaluation.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n'
    )
    if failures:
        (root / 'status.json').write_text(
            json.dumps(
                {
                    'run_id': os.environ.get('GLASSLAB_RUNNER_EXPERIMENT_ID'),
                    'status': 'failed',
                    'detail': 'immutable task integrity contract rejected the result',
                },
                indent=2,
                sort_keys=True,
            )
            + '\n'
        )
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
