from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    entrypoint = json.loads(os.environ['GLASSLAB_EXPERIMENT_ENTRYPOINT_JSON'])
    if not isinstance(entrypoint, list) or not all(
        isinstance(item, str) and item for item in entrypoint
    ):
        raise ValueError('experiment entrypoint must be a non-empty string list')
    experiment = subprocess.run(entrypoint, check=False)
    if experiment.returncode != 0:
        return experiment.returncode

    run_id = os.environ['GLASSLAB_RUNNER_EXPERIMENT_ID']
    output_root = Path(os.environ['GLASSLAB_RUNNER_ARTIFACTS_ROOT']) / run_id
    os.environ.setdefault('GLASSLAB_OUTPUT_DIR', str(output_root))
    os.environ.setdefault(
        'GLASSLAB_EVALUATION_INPUT',
        str(output_root / 'result.json'),
    )
    evaluator = os.environ['GLASSLAB_EVALUATION_ENTRY_POINT']
    return subprocess.run([sys.executable, evaluator], check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
