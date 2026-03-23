from __future__ import annotations

import json
import traceback

from .config import Settings
from .runner import run_experiment, write_json, write_supporting_artifacts


def main() -> None:
    settings = Settings()
    try:
        result = run_experiment(settings)
        write_supporting_artifacts(settings, result, status='succeeded')
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        settings.artifact_dir.mkdir(parents=True, exist_ok=True)
        result_payload = {
            'experiment_id': settings.experiment_id,
            'trace_id': settings.trace_id,
            'status': 'failed',
            'error': str(exc),
            'traceback': traceback.format_exc(),
            'artifact_dir': str(settings.artifact_dir),
        }
        write_json(settings.artifact_dir / 'result_payload.json', result_payload)
        write_supporting_artifacts(settings, result_payload, status='failed', error=str(exc))
        raise


if __name__ == '__main__':
    main()
