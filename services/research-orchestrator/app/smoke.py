from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

from .cluster import FakeClusterExecutor
from .config import SERVICE_ROOT, Settings
from .contract_candidates import ContractCandidateManager
from .contracts import EvaluationContractResolver
from .discord_adapter import DisabledDiscordAdapter
from .engine import ResearchOrchestrator
from .mock_runtime import ScriptedMockRuntime
from .policy import ActionPolicy
from .schemas import (
    ApprovalStatus,
    RunCreateRequest,
    RunState,
    SourceType,
)
from .storage import SqliteStore
from .workspaces import WorkspaceManager


RUNNER_IMAGE = 'ghcr.io/offensivegeneric/glasslab-smoke-runner:test'


def _create_repo(root: Path) -> Path:
    repo = root / 'approved-repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-b', 'main'], cwd=repo, check=True)
    subprocess.run(
        ['git', 'config', 'user.email', 'smoke@glasslab.local'],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ['git', 'config', 'user.name', 'Glasslab Smoke'],
        cwd=repo,
        check=True,
    )
    (repo / 'README.md').write_text('# Smoke repository\n')
    (repo / 'configs').mkdir()
    (repo / 'configs' / 'baseline.yaml').write_text('learning_rate: 0.0001\n')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(
        ['git', 'commit', '-m', 'Initialize smoke repository'],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


def run_smoke() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix='glasslab-orchestrator-smoke-') as raw:
        root = Path(raw)
        repo = _create_repo(root)
        # Knowledge smoke setup: a small allowlisted directory mirrors the
        # deployment's approved knowledge root, so ingest -> retrieve -> cite
        # can be exercised without any external model or cluster.
        approved = root / 'knowledge-approved'
        approved.mkdir()
        (approved / 'technique-card.md').write_text(
            'Technique card: metric-search over GPU clusters. Prefer cosine '
            'similarity for embedding retrieval and report verified metrics '
            'with a fixed seed.'
        )
        settings = Settings(
            database_path=str(root / 'orchestrator.db'),
            workspace_root=str(root / 'runs'),
            artifact_root=str(root / 'artifacts'),
            approved_repo_path=str(repo),
            approved_repo_ref='main',
            evaluation_contract_root=str(
                SERVICE_ROOT / 'evaluation-contracts'
            ),
            permitted_job_images=[RUNNER_IMAGE],
            cluster_execution_mode='fake',
            promoted_contract_root=str(root / 'trusted-contracts'),
            sealed_contract_candidate_root=str(root / 'contract-candidates'),
            trusted_contract_catalog_path=str(
                root / 'trusted-contracts' / 'catalog.json'
            ),
            shared_mount_root=str(root),
            task_bundle_root=str(root / 'task-bundles'),
            task_asset_root=str(root / 'task-assets'),
            dataset_upload_root=str(root / 'dataset-uploads'),
            benchmark_dataset_catalog_path=str(
                root / 'datasets' / 'catalog.json'
            ),
            knowledge_root=str(root / 'knowledge'),
            knowledge_allowlist_roots=[str(approved)],
            one_active_run=True,
            maximum_parallel_jobs=2,
        )
        store = SqliteStore(settings.database_path)
        cluster = FakeClusterExecutor()
        engine = ResearchOrchestrator(
            settings=settings,
            store=store,
            runtime=ScriptedMockRuntime(runner_image=RUNNER_IMAGE),
            workspaces=WorkspaceManager(
                workspace_root=settings.workspace_root,
                approved_repo_path=settings.approved_repo_path,
                approved_repo_ref=settings.approved_repo_ref,
            ),
            contracts=EvaluationContractResolver(
                settings.promoted_contract_root,
                fallback_roots=[settings.evaluation_contract_root],
            ),
            contract_candidates=ContractCandidateManager(
                sealed_root=settings.sealed_contract_candidate_root,
                promoted_root=settings.promoted_contract_root,
                catalog_path=settings.trusted_contract_catalog_path,
                shared_mount_root=settings.shared_mount_root,
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
        source = engine.knowledge.ingest_source(
            source_type=SourceType.TECHNIQUE_CARD,
            path=str(approved / 'technique-card.md'),
            title='GPU metric-search technique card',
        )
        # The technique card becomes the approved knowledge the mock agents
        # will retrieve and cite; its stable knowledge:// evidence URI is
        # returned in the smoke summary to prove the citable surface.
        run = engine.create_run(
            RunCreateRequest(
                objective='Prove the complete bounded orchestrator smoke workflow.'
            )
        )
        assert run.state == RunState.AWAITING_PROTOCOL_APPROVAL
        protocol_action = next(
            action
            for action in store.list_actions(run.run_id)
            if action.type == 'approve_protocol'
            and action.approval_status == ApprovalStatus.PENDING
        )
        engine.approve_action(
            protocol_action.action_id,
            reviewer='smoke-human',
            reason='Protocol approved for smoke test.',
        )
        run = store.get_run(run.run_id)
        assert run.state == RunState.AWAITING_EXECUTION_APPROVAL
        execution_action = next(
            action
            for action in store.list_actions(run.run_id)
            if action.type == 'submit_experiment_matrix'
            and action.approval_status == ApprovalStatus.PENDING
        )
        engine.approve_action(
            execution_action.action_id,
            reviewer='smoke-human',
            reason='Fake execution approved.',
        )
        for job in store.list_jobs(run.run_id):
            assert job.external_run_id is not None
            cluster.complete(
                job.external_run_id,
                metrics={'score': 0.8 if job.variant_name == 'candidate' else 0.6},
            )
        engine.reconcile_run(run.run_id)
        run = store.get_run(run.run_id)
        assert run.state == RunState.AWAITING_FINAL_ACCEPTANCE
        report_action = next(
            action
            for action in store.list_actions(run.run_id)
            if action.type == 'accept_final_report'
            and action.approval_status == ApprovalStatus.PENDING
        )
        engine.approve_action(
            report_action.action_id,
            reviewer='smoke-human',
            reason='Report accepted.',
        )
        run = store.get_run(run.run_id)
        assert run.state == RunState.COMPLETE
        # Knowledge assertions: every completed run records durable context
        # packets, at least one turn actually consumed ranked sources, and the
        # attachment was logged as an event so the packet is citable with a
        # knowledge://context:<id> evidence URI.
        packets = store.list_context_packets(run.run_id)
        assert packets, 'completed smoke run must record context packets'
        retrieved = [p for p in packets if p.ranked_sources]
        assert retrieved, 'at least one turn must consume retrieved context'
        attached_events = [
            event
            for event in store.list_events(run.run_id)
            if event.event_type == 'agent.context_attached'
        ]
        assert attached_events, 'context attachment events must be recorded'
        assert (
            engine.knowledge.get_context_packet(packets[0].packet_id)
            .evidence_uri()
            == f'knowledge://context:{packets[0].packet_id}'
        )
        return {
            'run_id': run.run_id,
            'state': run.state.value,
            'turns': len(store.list_turns(run.run_id)),
            'jobs': len(store.list_jobs(run.run_id)),
            'artifacts': len(store.list_artifacts(run.run_id)),
            'events': len(store.list_events(run.run_id)),
            'protocol_path': run.protocol_path,
            'report_path': str(Path(run.reports_path) / 'report.md'),
            'knowledge_sources': len(store.list_knowledge_sources()),
            'context_packets': len(packets),
            'citable_packet': packets[0].evidence_uri(),
            'ingested_source': source.evidence_uri(),
        }


def main() -> int:
    print(json.dumps(run_smoke(), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
