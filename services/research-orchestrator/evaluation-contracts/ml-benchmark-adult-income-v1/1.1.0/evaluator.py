from __future__ import annotations

import json
import os
from pathlib import Path


REQUIRED = {
    'accuracy', 'balanced_accuracy', 'precision', 'recall', 'f1', 'roc_auc',
    'headline_ci_low', 'headline_ci_high', 'bootstrap_resamples', 'test_rows',
}


def main() -> int:
    root = Path(os.environ['GLASSLAB_OUTPUT_DIR'])
    failures: list[str] = []
    try:
        metrics = json.loads((root / 'metrics.json').read_text())
    except Exception as exc:
        metrics = {}
        failures.append(f'metrics.json is unavailable or invalid: {exc}')
    missing = sorted(REQUIRED - set(metrics))
    if missing:
        failures.append('missing metrics: ' + ', '.join(missing))
    if metrics.get('test_rows') != 16281:
        failures.append('test_rows must equal the official 16,281-row split')
    if int(metrics.get('bootstrap_resamples', 0)) < 1000:
        failures.append('bootstrap_resamples must be at least 1000')
    for relative in ('report.md', 'tables/metrics.csv', 'tables/fairness.csv'):
        if not (root / relative).is_file():
            failures.append(f'missing required evidence: {relative}')
    score = round(100 * max(0, len(REQUIRED) - len(missing)) / len(REQUIRED), 2)
    result = {
        'rubric_score': 0.0 if failures else score,
        'integrity_pass': not failures,
        'failures': failures,
        'contract_id': os.environ['GLASSLAB_EVALUATION_CONTRACT_ID'],
        'contract_version': os.environ['GLASSLAB_EVALUATION_CONTRACT_VERSION'],
        'contract_digest': os.environ['GLASSLAB_EVALUATION_CONTRACT_DIGEST'],
    }
    (root / 'evaluation.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    if failures:
        status = {
            'run_id': os.environ.get('GLASSLAB_RUNNER_EXPERIMENT_ID'),
            'status': 'failed',
            'detail': 'immutable evaluation contract rejected the result',
        }
        (root / 'status.json').write_text(json.dumps(status, indent=2, sort_keys=True) + '\n')
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
