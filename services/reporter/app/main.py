from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from services.common.schemas import Metrics, RunManifest


def render_report(manifest: RunManifest, metrics: Metrics, evaluator_output: dict[str, Any] | None = None) -> str:
    winning_note = None
    if evaluator_output:
        winning_note = evaluator_output.get('best_run_id')

    primary_metric = None
    if metrics.primary_metric:
        primary_metric = next((item for item in metrics.values if item.name == metrics.primary_metric), None)

    lines = ['# Glasslab Run Memo', '']
    lines.extend(['## Objective', '', manifest.objective, ''])
    lines.extend(['## Workflows Run', '', f'- Workflow: `{manifest.workflow_id}`', f'- Family: `{manifest.workflow_family}`', f'- Models: `{", ".join(manifest.requested_models)}`', ''])
    lines.extend(['## Results', ''])
    if primary_metric is not None:
        lines.append(
            f'- Primary metric `{primary_metric.name}` on `{primary_metric.split or "unspecified"}`: `{primary_metric.value}`'
        )
    if metrics.runtime_seconds is not None:
        lines.append(f'- Runtime seconds: `{metrics.runtime_seconds}`')
    if winning_note:
        lines.append(f'- Evaluator selected best run: `{winning_note}`')
    if not primary_metric and metrics.runtime_seconds is None and not winning_note:
        lines.append('- No measured result fields were present in the input payload.')
    lines.extend(['', '## Caveats', ''])
    if evaluator_output:
        lines.append('- This memo includes evaluator output and should be read alongside comparison.json for machine-readable ranking.')
    else:
        lines.append('- This memo covers a single run and has no cross-run evaluator comparison attached.')
    lines.extend(['', '## Next Recommended Steps', ''])
    if winning_note and winning_note != manifest.run_id:
        lines.append('- Inspect why this run did not win the evaluator comparison before promoting it.')
    elif primary_metric is not None:
        lines.append('- Review artifacts and decide whether the measured result justifies a follow-up run or promotion.')
    else:
        lines.append('- Inspect the artifact bundle and complete missing measurements before drawing conclusions.')
    return '\n'.join(lines)


def write_report(
    manifest_path: Path,
    metrics_path: Path,
    output_path: Path,
    evaluator_path: Path | None = None,
) -> str:
    manifest = RunManifest.model_validate_json(manifest_path.read_text())
    metrics = Metrics.model_validate_json(metrics_path.read_text())
    evaluator_output = json.loads(evaluator_path.read_text()) if evaluator_path else None
    report = render_report(manifest, metrics, evaluator_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Render a deterministic Glasslab v2 run memo.')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--metrics', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--evaluator', required=False)
    args = parser.parse_args()

    write_report(
        manifest_path=Path(args.manifest),
        metrics_path=Path(args.metrics),
        output_path=Path(args.output),
        evaluator_path=Path(args.evaluator) if args.evaluator else None,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
