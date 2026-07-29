from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from app.config import SERVICE_ROOT
from app.contracts import EvaluationContractResolver


CONTRACT_ROOT = (
    SERVICE_ROOT
    / 'evaluation-contracts'
    / 'generic-task-integrity-v1'
    / '1.0.0'
)


def _run_evaluator(root: Path, task_spec: dict) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        'GLASSLAB_OUTPUT_DIR': str(root),
        'GLASSLAB_GENERIC_CONFIG_JSON': json.dumps({'task_spec': task_spec}),
        'GLASSLAB_EVALUATION_CONTRACT_ID': 'generic-task-integrity-v1',
        'GLASSLAB_EVALUATION_CONTRACT_VERSION': '1.0.0',
        'GLASSLAB_EVALUATION_CONTRACT_DIGEST': 'a' * 64,
    }
    return subprocess.run(
        [sys.executable, str(CONTRACT_ROOT / 'evaluator.py')],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_generic_contract_checksum_and_dynamic_requirements(tmp_path: Path) -> None:
    resolved = EvaluationContractResolver(
        str(SERVICE_ROOT / 'evaluation-contracts')
    ).resolve('generic-task-integrity-v1', '1.0.0')
    assert len(resolved.digest) == 64
    (tmp_path / 'metrics.json').write_text('{"accuracy": 0.9}\n')
    (tmp_path / 'report.md').write_text('# Report\n')
    tables = tmp_path / 'tables'
    tables.mkdir()
    (tables / 'metrics.csv').write_text('accuracy\n0.9\n')
    result = _run_evaluator(
        tmp_path,
        {
            'required_metric_keys': ['accuracy'],
            'required_artifacts': ['tables/metrics.csv'],
        },
    )
    assert result.returncode == 0
    assert json.loads(
        (tmp_path / 'evaluation.json').read_text()
    )['integrity_pass']


def test_generic_contract_rejects_missing_task_evidence(tmp_path: Path) -> None:
    (tmp_path / 'metrics.json').write_text('{}\n')
    (tmp_path / 'report.md').write_text('# Report\n')
    result = _run_evaluator(
        tmp_path,
        {
            'required_metric_keys': ['accuracy'],
            'required_artifacts': ['tables/metrics.csv'],
        },
    )
    assert result.returncode == 1
    evaluation = json.loads((tmp_path / 'evaluation.json').read_text())
    assert not evaluation['integrity_pass']
    assert any('missing metrics' in item for item in evaluation['failures'])
