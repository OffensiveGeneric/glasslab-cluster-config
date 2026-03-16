from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.common.schemas import Metrics, RunManifest, RunStatus

from .models import ComparedRun, ComparisonResult, RankedRun


def load_bundle(bundle_dir: Path) -> ComparedRun:
    manifest = RunManifest.model_validate_json((bundle_dir / 'run_manifest.json').read_text())
    metrics = Metrics.model_validate_json((bundle_dir / 'metrics.json').read_text())
    status = RunStatus.model_validate_json((bundle_dir / 'status.json').read_text())

    primary_metric = None
    if metrics.primary_metric:
        primary_metric = next((item for item in metrics.values if item.name == metrics.primary_metric), None)

    return ComparedRun(
        run_id=manifest.run_id,
        workflow_id=manifest.workflow_id,
        workflow_family=manifest.workflow_family,
        models=manifest.requested_models,
        status=status.status,
        primary_metric_name=metrics.primary_metric,
        primary_metric_value=primary_metric.value if primary_metric else None,
        primary_metric_direction=primary_metric.direction if primary_metric else None,
        runtime_seconds=metrics.runtime_seconds,
    )


def rank_runs(runs: list[ComparedRun]) -> tuple[list[ComparedRun], str]:
    if not runs:
        return [], 'no runs supplied'

    def sort_key(item: ComparedRun):
        status_weight = 0 if item.status == 'succeeded' else 1
        metric_missing = 1 if item.primary_metric_value is None else 0
        direction = item.primary_metric_direction or 'maximize'
        if item.primary_metric_value is None:
            metric_sort = 0.0
        elif direction == 'minimize':
            metric_sort = item.primary_metric_value
        else:
            metric_sort = -item.primary_metric_value
        runtime_sort = item.runtime_seconds if item.runtime_seconds is not None else float('inf')
        return (status_weight, metric_missing, metric_sort, runtime_sort, item.run_id)

    ranked = sorted(runs, key=sort_key)
    basis = 'succeeded status, metric presence, primary metric, runtime seconds, run_id'
    return ranked, basis


def compare_bundles(bundle_dirs: list[Path]) -> ComparisonResult:
    compared_runs = [load_bundle(path) for path in bundle_dirs]
    ranked_runs, basis = rank_runs(compared_runs)
    ranking = [
        RankedRun(position=index, run_id=item.run_id, reason='ordered by succeeded status, metric presence, metric, then runtime')
        for index, item in enumerate(ranked_runs, start=1)
    ]
    best_run_id = ranked_runs[0].run_id if ranked_runs else None
    return ComparisonResult(
        compared_runs=compared_runs,
        ranking=ranking,
        best_run_id=best_run_id,
        comparison_basis=basis,
    )


def render_summary(result: ComparisonResult) -> str:
    lines = ['# Comparison Summary', '']
    if result.best_run_id is None:
        lines.extend(['No runs were supplied.', ''])
        return '\n'.join(lines)

    lines.append(f'Best run: `{result.best_run_id}`')
    lines.append('')
    lines.append('## Compared Runs')
    lines.append('')
    for run in sorted(result.compared_runs, key=lambda item: item.run_id):
        lines.append(
            f'- `{run.run_id}` | workflow `{run.workflow_id}` | family `{run.workflow_family}` | '
            f'models `{", ".join(run.models)}` | status `{run.status}` | '
            f'primary metric `{run.primary_metric_name}`={run.primary_metric_value} | runtime `{run.runtime_seconds}`s'
        )
    lines.append('')
    lines.append(f'Comparison basis: {result.comparison_basis}')
    return '\n'.join(lines)


def write_outputs(bundle_dirs: list[Path], output_dir: Path) -> ComparisonResult:
    result = compare_bundles(bundle_dirs)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'comparison.json').write_text(json.dumps(result.model_dump(mode='json'), indent=2) + '\n')
    (output_dir / 'summary.md').write_text(render_summary(result) + '\n')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Compare Glasslab v2 run bundles.')
    parser.add_argument('--bundle-dir', action='append', required=True, dest='bundle_dirs')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    write_outputs([Path(path) for path in args.bundle_dirs], Path(args.output_dir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
