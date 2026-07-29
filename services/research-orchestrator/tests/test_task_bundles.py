from __future__ import annotations

from hashlib import sha256
import io
from pathlib import Path
import zipfile

import pytest

from app.schemas import TaskAssetProposal, TaskSpecProposal
from app.task_bundles import (
    RUNTIME_PROFILES,
    TaskBundleError,
    TaskBundleManager,
)
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
    catalog_path = tmp_path / 'catalog.json'
    catalog_path.write_text('{}')
    return TaskBundleManager(
        root=str(tmp_path / 'task-bundles'),
        shared_mount_root=str(tmp_path),
        dataset_catalog_path=str(catalog_path),
        task_asset_root=str(tmp_path / 'task-assets'),
    )


def test_import_task_bundle_is_immutable_and_idempotent(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    content = _archive()
    proposal = TaskSpecProposal(
        schema_version='glasslab-task-spec-v1',
        display_name='Adult Income Classification',
        runtime_profile='cpu-ml-standard-v1',
        required_artifacts=['tables/metrics.csv'],
        required_metric_keys=['accuracy'],
        rationale='Small tabular classification task.',
    )
    first = manager.compile(manager.stage_archive(
        filename='ML_Benchmark_Adult_Income.zip',
        content=content,
    ), proposal)
    second = manager.compile(manager.stage_archive(
        filename='ML_Benchmark_Adult_Income.zip',
        content=content,
    ), proposal)
    assert first == second
    assert first.digest == sha256(content).hexdigest()
    assert Path(first.problem_path).read_text() == '# Adult task\n'
    assert Path(first.problem_path).stat().st_mode & 0o222 == 0
    assert first.compilation_source == 'honeydew-task-spec'
    assert first.workload_id == 'workspace-cpu-ml-v1'
    assert first.datasets == []


def test_import_task_bundle_rejects_path_traversal(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(TaskBundleError, match='unsafe'):
        manager.stage_archive(
            filename='ML_Benchmark_Adult_Income.zip',
            content=_archive(unsafe_name='../problem.md'),
        )


def test_task_preflight_reports_missing_inputs(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    proposal = TaskSpecProposal(
        schema_version='glasslab-task-spec-v1',
        display_name='Needs Private Data',
        runtime_profile='gpu-ml-standard-v1',
        missing_inputs=['private training split must be supplied'],
        rationale='The requested dataset has no approved public source.',
    )
    record = manager.compile(
        manager.stage_archive(filename='anything.zip', content=_archive()),
        proposal,
    )
    preflight = manager.preflight(
        record,
        permitted_images={
            RUNTIME_PROFILES['gpu-ml-standard-v1'].runner_image
        },
        evaluator_ready=True,
    )
    assert not preflight.ready
    assert not preflight.assets_ready
    assert 'private training split' in preflight.blocking_issues[0]


def test_task_asset_fetcher_rejects_non_public_url(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(TaskBundleError, match='public HTTPS'):
        manager.assets.fetch(
            task_digest='a' * 64,
            proposal=TaskAssetProposal(
                name='private_data',
                role='train',
                source_url='http://127.0.0.1/data.csv',
            ),
        )


def test_engine_compiles_arbitrary_task_name(orchestrator_bundle) -> None:
    _, _, _, runtime, engine = orchestrator_bundle
    record = engine.import_task_bundle(
        filename='new-contributor-task.zip',
        content=_archive(),
    )
    assert record.task_id == f'task-{record.digest[:16]}'
    assert record.task_spec is not None
    assert record.task_spec['required_metric_keys'] == ['accuracy']
    assert runtime.sessions == {}


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
