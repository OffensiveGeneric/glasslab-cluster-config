from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _read_from_path_or_uri(path_or_uri: str) -> str:
    parsed = urlparse(path_or_uri)
    if parsed.scheme == 's3':
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError('minio package is required for S3/MinIO URIs') from exc
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        client = Minio(
            'glasslab-minio.glasslab-v2.svc.cluster.local:9000',
            access_key=None,
            secret_key=None,
            secure=False,
        )
        obj = client.get_object(bucket, key)
        try:
            return obj.read().decode('utf-8')
        finally:
            obj.close()
            obj.release_ram()
    else:
        return Path(path_or_uri).read_text()


def _write_to_path_or_uri(path_or_uri: str, content: str) -> None:
    parsed = urlparse(path_or_uri)
    if parsed.scheme == 's3':
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError('minio package is required for S3/MinIO URIs') from exc
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        client = Minio(
            'glasslab-minio.glasslab-v2.svc.cluster.local:9000',
            access_key=None,
            secret_key=None,
            secure=False,
        )
        from io import BytesIO
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(bucket, key, BytesIO(content.encode('utf-8')), length=len(content.encode('utf-8')))
    else:
        p = Path(path_or_uri)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


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
    manifest_path: str,
    metrics_path: str,
    output_path: str,
    evaluator_path: str | None = None,
) -> str:
    manifest = RunManifest.model_validate_json(_read_from_path_or_uri(manifest_path))
    metrics = Metrics.model_validate_json(_read_from_path_or_uri(metrics_path))
    evaluator_output = json.loads(_read_from_path_or_uri(evaluator_path)) if evaluator_path else None
    report = render_report(manifest, metrics, evaluator_output)
    _write_to_path_or_uri(output_path, report + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Render a deterministic Glasslab v2 run memo.')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--metrics', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--evaluator', required=False)
    args = parser.parse_args()

    write_report(
        manifest_path=args.manifest,
        metrics_path=args.metrics,
        output_path=args.output,
        evaluator_path=args.evaluator if args.evaluator else None,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
