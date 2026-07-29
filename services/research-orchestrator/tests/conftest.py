from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from app.cluster import FakeClusterExecutor
from app.config import SERVICE_ROOT, Settings
from app.contracts import EvaluationContractResolver
from app.discord_adapter import DisabledDiscordAdapter
from app.engine import ResearchOrchestrator
from app.mock_runtime import ScriptedMockRuntime
from app.policy import ActionPolicy
from app.storage import SqliteStore
from app.workspaces import WorkspaceManager


RUNNER_IMAGE = 'ghcr.io/offensivegeneric/glasslab-test-runner:test'


def create_test_repo(root: Path) -> Path:
    repo = root / 'repo'
    repo.mkdir()
    subprocess.run(
        ['git', 'init', '-b', 'main'],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ['git', 'config', 'user.email', 'test@glasslab.local'],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ['git', 'config', 'user.name', 'Glasslab Test'],
        cwd=repo,
        check=True,
    )
    (repo / 'README.md').write_text('# Test repository\n')
    (repo / 'configs').mkdir()
    (repo / 'configs' / 'baseline.yaml').write_text('learning_rate: 0.0001\n')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(
        ['git', 'commit', '-m', 'Initialize'],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def orchestrator_bundle(tmp_path):
    repo = create_test_repo(tmp_path)
    settings = Settings(
        database_path=str(tmp_path / 'orchestrator.db'),
        workspace_root=str(tmp_path / 'runs'),
        artifact_root=str(tmp_path / 'artifacts'),
        approved_repo_path=str(repo),
        approved_repo_ref='main',
        evaluation_contract_root=str(SERVICE_ROOT / 'evaluation-contracts'),
        permitted_job_images=[RUNNER_IMAGE],
        cluster_execution_mode='fake',
        one_active_run=False,
        maximum_parallel_jobs=2,
    )
    store = SqliteStore(settings.database_path)
    cluster = FakeClusterExecutor()
    runtime = ScriptedMockRuntime(runner_image=RUNNER_IMAGE)
    engine = ResearchOrchestrator(
        settings=settings,
        store=store,
        runtime=runtime,
        workspaces=WorkspaceManager(
            workspace_root=settings.workspace_root,
            approved_repo_path=settings.approved_repo_path,
            approved_repo_ref=settings.approved_repo_ref,
        ),
        contracts=EvaluationContractResolver(
            settings.evaluation_contract_root
        ),
        policy=ActionPolicy(
            permitted_images=settings.permitted_job_images,
            maximum_cpu=settings.maximum_cpu,
            maximum_memory_gib=settings.maximum_memory_gib,
            maximum_gpus=settings.maximum_gpus,
            maximum_parallel_jobs=settings.maximum_parallel_jobs,
        ),
        cluster=cluster,
        discord=DisabledDiscordAdapter(),
    )
    return settings, store, cluster, runtime, engine
