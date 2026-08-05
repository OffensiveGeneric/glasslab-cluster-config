from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    entrypoint = json.loads(os.environ['GLASSLAB_EXPERIMENT_ENTRYPOINT_JSON'])
    experiment = subprocess.run(entrypoint, check=False)
    run_id = os.environ['GLASSLAB_RUNNER_EXPERIMENT_ID']
    output_root = Path(os.environ['GLASSLAB_RUNNER_ARTIFACTS_ROOT']) / run_id
    os.environ['GLASSLAB_OUTPUT_DIR'] = str(output_root)
    evaluator = subprocess.run(
        [sys.executable, os.environ['GLASSLAB_EVALUATION_ENTRY_POINT']],
        check=False,
    )
    return experiment.returncode or evaluator.returncode


if __name__ == '__main__':
    raise SystemExit(main())
