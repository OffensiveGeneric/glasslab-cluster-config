import json
from pathlib import Path

from app.main import write_report


def write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest_path = tmp_path / 'run_manifest.json'
    metrics_path = tmp_path / 'metrics.json'
    evaluator_path = tmp_path / 'comparison.json'
    manifest_path.write_text(
        json.dumps(
            {
                'run_id': 'run-20260316-001',
                'workflow_id': 'generic-tabular-benchmark',
                'workflow_family': 'tabular-benchmark',
                'display_name': 'Generic Tabular Benchmark',
                'objective': 'Benchmark approved models on Titanic.',
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
    metrics_path.write_text(
        json.dumps(
            {
                'run_id': 'run-20260316-001',
                'primary_metric': 'validation_accuracy',
                'values': [
                    {
                        'name': 'validation_accuracy',
                        'value': 0.85,
                        'direction': 'maximize',
                        'split': 'validation',
                    }
                ],
                'runtime_seconds': 38.4,
                'notes': [],
            }
        )
    )
    evaluator_path.write_text(json.dumps({'best_run_id': 'run-20260316-001'}))
    return manifest_path, metrics_path, evaluator_path


def test_write_report_includes_required_sections(tmp_path) -> None:
    manifest_path, metrics_path, evaluator_path = write_inputs(tmp_path)
    output_path = tmp_path / 'report.md'

    report = write_report(manifest_path, metrics_path, output_path, evaluator_path)

    assert '## Objective' in report
    assert '## Workflows Run' in report
    assert '## Results' in report
    assert '## Caveats' in report
    assert '## Next Recommended Steps' in report
    assert 'Evaluator selected best run' in report
    assert output_path.read_text().startswith('# Glasslab Run Memo')
