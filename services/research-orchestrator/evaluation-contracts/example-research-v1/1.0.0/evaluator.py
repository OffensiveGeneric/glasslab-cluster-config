from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    input_path = Path(os.environ.get('GLASSLAB_EVALUATION_INPUT', '/inputs/result.json'))
    output_root = Path(os.environ.get('GLASSLAB_OUTPUT_DIR', '/outputs'))
    contract_digest = os.environ['GLASSLAB_EVALUATION_CONTRACT_DIGEST']
    candidate = json.loads(input_path.read_text())
    raw_score = candidate.get('candidate', {}).get('score', 0.0)
    score = max(0.0, min(1.0, float(raw_score)))
    result = {
        'score': score,
        'passed': score >= 0.5,
        'contract_digest': contract_digest,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / 'evaluation.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n'
    )
    (output_root / 'metrics.json').write_text(
        json.dumps({'score': score}, indent=2, sort_keys=True) + '\n'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
