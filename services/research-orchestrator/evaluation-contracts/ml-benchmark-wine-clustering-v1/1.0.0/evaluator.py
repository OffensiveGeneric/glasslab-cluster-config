from __future__ import annotations

import json
import os
from pathlib import Path


REQUIRED = {
    'algorithm_count', 'sample_count', 'silhouette', 'davies_bouldin',
    'adjusted_rand', 'normalized_mutual_info', 'stability_seeds',
    'pca_variance_2d',
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
    if metrics.get('sample_count') != 178:
        failures.append('sample_count must equal the official 178-row dataset')
    if int(metrics.get('algorithm_count', 0)) < 3:
        failures.append('at least three clustering algorithms are required')
    if int(metrics.get('stability_seeds', 0)) < 10:
        failures.append('stability_seeds must be at least 10')
    for relative in ('report.md', 'plots/clusters.png', 'tables/comparison.csv'):
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
