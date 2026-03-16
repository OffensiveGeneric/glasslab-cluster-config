import json
from pathlib import Path

from app.main import write_outputs


def write_bundle(path: Path, run_id: str, metric: float, runtime_seconds: float) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / 'run_manifest.json').write_text(
        json.dumps(
            {
                'run_id': run_id,
                'workflow_id': 'generic-tabular-benchmark',
                'workflow_family': 'tabular-benchmark',
                'display_name': 'Generic Tabular Benchmark',
                'objective': 'Benchmark approved models.',
                'submitted_by': 'tester',
                'submitted_at': '2026-03-16T18:00:00Z',
                'inputs': {'dataset_name': 'titanic'},
                'requested_models': ['random_forest'],
                'resource_profile': 'cpu-small',
                'runner_image': 'ghcr.io/offensivegeneric/glasslab-tabular-runner:0.1.0',
                'evaluator_type': 'tabular-metric-max',
                'approval_tier': 'tier-2-approved-execution',
                'expected_artifacts': {'required': ['run_manifest.json'], 'optional': []},
            }
        )
    )
    (path / 'metrics.json').write_text(
        json.dumps(
            {
                'run_id': run_id,
                'primary_metric': 'validation_accuracy',
                'values': [
                    {
                        'name': 'validation_accuracy',
                        'value': metric,
                        'direction': 'maximize',
                        'split': 'validation',
                    }
                ],
                'runtime_seconds': runtime_seconds,
                'notes': [],
            }
        )
    )
    (path / 'status.json').write_text(
        json.dumps(
            {
                'run_id': run_id,
                'status': 'succeeded',
                'updated_at': '2026-03-16T18:01:00Z',
                'detail': 'ok',
            }
        )
    )


def test_write_outputs_ranks_best_run(tmp_path) -> None:
    bundle_a = tmp_path / 'run-a'
    bundle_b = tmp_path / 'run-b'
    output_dir = tmp_path / 'output'
    write_bundle(bundle_a, 'run-a', 0.81, 42.0)
    write_bundle(bundle_b, 'run-b', 0.85, 38.0)

    result = write_outputs([bundle_a, bundle_b], output_dir)

    assert result.best_run_id == 'run-b'
    comparison = json.loads((output_dir / 'comparison.json').read_text())
    assert comparison['ranking'][0]['run_id'] == 'run-b'
    summary = (output_dir / 'summary.md').read_text()
    assert 'Best run: `run-b`' in summary
    assert 'Comparison basis:' in summary
