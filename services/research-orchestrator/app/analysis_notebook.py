"""Build self-contained Jupyter notebooks from digest-verified evaluator output.

Only artifacts that pass VerifiedArtifactReader (sha256 + path confinement) are
embedded, so a notebook is a pure, immutable analysis surface backed by
provenance records; it is explicitly not authoritative evidence.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .artifact_delivery import ArtifactDeliveryError, VerifiedArtifactReader
from .schemas import ArtifactRecord


def _code_cell(source: str) -> dict[str, Any]:
    return {
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [],
        'source': source.splitlines(keepends=True),
    }


def _markdown_cell(source: str) -> dict[str, Any]:
    return {
        'cell_type': 'markdown',
        'metadata': {},
        'source': source.splitlines(keepends=True),
    }


def build_analysis_notebook(
    *,
    run_id: str,
    job_id: str,
    artifacts: list[ArtifactRecord],
    shared_mount_root: str,
    maximum_source_bytes: int = 2 * 1024 * 1024,
) -> bytes:
    reader = VerifiedArtifactReader(shared_mount_root)
    metrics: dict[str, Any] = {}
    tables: dict[str, str] = {}
    provenance: list[dict[str, str]] = []

    for artifact in artifacts:
        name = Path(artifact.uri).name
        try:
            if name == 'metrics.json':
                payload = reader.read(
                    artifact,
                    maximum_bytes=maximum_source_bytes,
                )
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    metrics = parsed
                    provenance.append(
                        {'uri': artifact.uri, 'sha256': artifact.sha256}
                    )
            elif artifact.type.startswith('tables/') and name.endswith('.csv'):
                payload = reader.read(
                    artifact,
                    maximum_bytes=maximum_source_bytes,
                )
                tables[artifact.type] = payload.decode('utf-8')
                provenance.append(
                    {'uri': artifact.uri, 'sha256': artifact.sha256}
                )
        except (ArtifactDeliveryError, UnicodeDecodeError, json.JSONDecodeError):
            continue

    if not metrics and not tables:
        raise ArtifactDeliveryError(
            'analysis notebook requires verified metrics.json or CSV tables'
        )

    embedded = (
        'import json\n'
        f'METRICS = json.loads({json.dumps(metrics, sort_keys=True)!r})\n'
        f'TABLES = json.loads({json.dumps(tables, sort_keys=True)!r})\n'
    )
    # The data is embedded as literals (not loaded at runtime from the shared
    # mount) so the exported notebook is self-contained and frozen; it can be
    # replayed anywhere without access to the original artifacts.
    visualization = '''from io import StringIO
import pandas as pd
import matplotlib.pyplot as plt

display(pd.json_normalize(METRICS, sep='.').T.rename(columns={0: 'value'}))

numeric_metrics = {
    key: value
    for key, value in pd.json_normalize(METRICS, sep='.').iloc[0].items()
    if isinstance(value, (int, float)) and not isinstance(value, bool)
}
if numeric_metrics:
    pd.Series(numeric_metrics).sort_values().plot.barh(
        figsize=(9, max(3, len(numeric_metrics) * 0.3)),
        title='Recorded numeric metrics',
    )
    plt.tight_layout()
    plt.show()

for table_name, csv_text in TABLES.items():
    frame = pd.read_csv(StringIO(csv_text))
    display(frame)
    numeric = frame.select_dtypes(include='number')
    if not numeric.empty:
        plot_frame = numeric.head(40)
        plot_frame.plot(
            kind='bar',
            figsize=(10, 4),
            title=table_name,
        )
        plt.tight_layout()
        plt.show()
'''
    notebook = {
        'cells': [
            _markdown_cell(
                '# Glasslab Analysis Notebook\n\n'
                f'Run `{run_id}`; job `{job_id}`. This notebook is derived '
                'from digest-verified evaluator outputs. It is an analysis '
                'surface, not authoritative evidence.\n'
            ),
            _code_cell(embedded),
            _code_cell(visualization),
            _markdown_cell(
                '## Provenance\n\n'
                + '\n'.join(
                    f"- `{item['uri']}` (`{item['sha256']}`)"
                    for item in provenance
                )
                + '\n'
            ),
        ],
        'metadata': {
            'glasslab': {
                'kind': 'verified-result-analysis',
                'run_id': run_id,
                'job_id': job_id,
                'source_artifacts': provenance,
            },
            'kernelspec': {
                'display_name': 'Python 3',
                'language': 'python',
                'name': 'python3',
            },
            'language_info': {'name': 'python', 'version': '3'},
        },
        'nbformat': 4,
        'nbformat_minor': 5,
    }
    return (json.dumps(notebook, indent=2, sort_keys=True) + '\n').encode()


def write_analysis_notebook(
    *,
    destination: Path,
    run_id: str,
    job_id: str,
    artifacts: list[ArtifactRecord],
    shared_mount_root: str,
) -> tuple[str, list[dict[str, str]]]:
    content = build_analysis_notebook(
        run_id=run_id,
        job_id=job_id,
        artifacts=artifacts,
        shared_mount_root=shared_mount_root,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.ipynb.tmp')
    temporary.write_bytes(content)
    # Atomic replace: a partially written notebook can never be observed at the
    # final path, and the digest returned below always matches the bytes that
    # landed on disk.
    temporary.replace(destination)
    notebook = json.loads(content)
    return (
        sha256(content).hexdigest(),
        notebook['metadata']['glasslab']['source_artifacts'],
    )
