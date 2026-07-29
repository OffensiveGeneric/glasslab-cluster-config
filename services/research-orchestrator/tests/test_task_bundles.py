from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile

import pytest

from app.task_bundles import TaskBundleError, TaskBundleManager
from app.workspaces import WorkspaceManager


def _archive(*, unsafe_name: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as handle:
        handle.writestr(
            unsafe_name or 'ML_Benchmark_Adult_Income/problem.md',
            '# Adult task\n',
        )
        handle.writestr(
            'ML_Benchmark_Adult_Income/eval_agent_prompt.md',
            '# Rubric\n',
        )
    return output.getvalue()


def _manager(tmp_path: Path) -> TaskBundleManager:
    datasets = tmp_path / 'datasets'
    datasets.mkdir()
    train = datasets / 'adult.data'
    test = datasets / 'adult.test'
    train.write_text('train\n')
    test.write_text('test\n')
    catalog = {
        'adult_train': {
            'uri': 's3://datasets/adult.data',
            'sha256': sha256(train.read_bytes()).hexdigest(),
            'role': 'train',
            'contains_labels': True,
        },
        'adult_test': {
            'uri': 's3://datasets/adult.test',
            'sha256': sha256(test.read_bytes()).hexdigest(),
            'role': 'test',
            'contains_labels': True,
        },
    }
    catalog_path = tmp_path / 'catalog.json'
    catalog_path.write_text(json.dumps(catalog))
    return TaskBundleManager(
        root=str(tmp_path / 'task-bundles'),
        shared_mount_root=str(tmp_path),
        dataset_catalog_path=str(catalog_path),
    )


def test_import_task_bundle_is_immutable_and_idempotent(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    content = _archive()
    first = manager.import_archive(
        filename='ML_Benchmark_Adult_Income.zip',
        content=content,
    )
    second = manager.import_archive(
        filename='ML_Benchmark_Adult_Income.zip',
        content=content,
    )
    assert first == second
    assert first.digest == sha256(content).hexdigest()
    assert Path(first.problem_path).read_text() == '# Adult task\n'
    assert Path(first.problem_path).stat().st_mode & 0o222 == 0
    assert [item.name for item in first.datasets] == [
        'adult_train',
        'adult_test',
    ]


def test_import_task_bundle_rejects_path_traversal(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(TaskBundleError, match='unsafe'):
        manager.import_archive(
            filename='ML_Benchmark_Adult_Income.zip',
            content=_archive(unsafe_name='../problem.md'),
        )


def test_source_bundle_packaging_is_deterministic(
    tmp_path: Path,
    orchestrator_bundle,
) -> None:
    _, _, _, _, engine = orchestrator_bundle
    run_id = 'deterministic-source'
    paths = engine.workspaces.prepare(run_id)
    source = paths.beaker / 'benchmark-workspace' / 'adult-income'
    source.mkdir(parents=True)
    (source / 'run.py').write_text('print("ok")\n')
    first_path, first_digest = engine.workspaces.package_source_bundle(
        run_id=run_id,
        source_subdirectory='benchmark-workspace/adult-income',
    )
    first_bytes = first_path.read_bytes()
    second_path, second_digest = engine.workspaces.package_source_bundle(
        run_id=run_id,
        source_subdirectory='benchmark-workspace/adult-income',
    )
    assert second_path.read_bytes() == first_bytes
    assert second_digest == first_digest
