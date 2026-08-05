from __future__ import annotations

import json
import os
from pathlib import Path


REQUIRED = {
    'train_rows', 'test_rows', 'linear_probe_accuracy',
    'raw_linear_probe_accuracy', 'knn_5_accuracy', 'knn_20_accuracy',
    'retrieval_precision_at_10', 'bootstrap_resamples', 'embedding_dimension',
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
    if metrics.get('train_rows') != 60000 or metrics.get('test_rows') != 10000:
        failures.append('official 60,000/10,000 train/test split is required')
    if int(metrics.get('bootstrap_resamples', 0)) < 2000:
        failures.append('bootstrap_resamples must be at least 2000')
    for relative in (
        'report.md',
        'plots/training_curve.png',
        'plots/embeddings.png',
        'tables/class_metrics.csv',
    ):
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
