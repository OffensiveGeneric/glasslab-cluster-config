from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


SERVICE_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix='GLASSLAB_ORCHESTRATOR_',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'glasslab-research-orchestrator'
    app_version: str = '0.1.0'
    database_path: str = '/tmp/glasslab-research-orchestrator/orchestrator.db'
    workspace_root: str = '/tmp/glasslab-research-orchestrator/runs'
    artifact_root: str = '/tmp/glasslab-research-orchestrator/artifacts'
    # Knowledge store: chunk sizing and the per-turn retrieval budget bound
    # context cost regardless of model or content; the allowlist roots are the
    # only places ingestion may read from (in production these are the mounted
    # cluster-config docs and evaluation-contract directories).
    knowledge_root: str = '/tmp/glasslab-research-orchestrator/knowledge'
    knowledge_chunk_size: int = 1500
    knowledge_chunk_overlap: int = 150
    knowledge_max_source_bytes: int = 2 * 1024 * 1024
    knowledge_max_results: int = 10
    knowledge_token_budget: int = 4000
    knowledge_allowlist_roots: Annotated[list[str], NoDecode] = [
        '/workspace/cluster-config/docs',
        '/workspace/cluster-config/services/research-orchestrator/evaluation-contracts',
    ]
    evidence_excerpt_max_bytes: int = 32 * 1024
    approved_repo_path: str = '/workspace/cluster-config'
    approved_repo_ref: str = 'main'
    evaluation_contract_root: str = str(SERVICE_ROOT / 'evaluation-contracts')
    promoted_contract_root: str = (
        '/tmp/glasslab-research-orchestrator/trusted-contracts'
    )
    sealed_contract_candidate_root: str = (
        '/tmp/glasslab-research-orchestrator/contract-candidates'
    )
    trusted_contract_catalog_path: str = (
        '/tmp/glasslab-research-orchestrator/trusted-contracts/catalog.json'
    )
    shared_mount_root: str = '/tmp/glasslab-research-orchestrator'
    task_bundle_root: str = '/tmp/glasslab-research-orchestrator/task-bundles'
    task_asset_root: str = '/tmp/glasslab-research-orchestrator/task-assets'
    maximum_task_asset_bytes: int = 2 * 1024 * 1024 * 1024
    dataset_upload_root: str = (
        '/tmp/glasslab-research-orchestrator/dataset-uploads'
    )
    maximum_dataset_upload_bytes: int = 2 * 1024 * 1024 * 1024
    maximum_discord_dataset_upload_bytes: int = 100 * 1024 * 1024
    maximum_discord_artifact_bundle_bytes: int = 24 * 1024 * 1024
    benchmark_dataset_catalog_path: str = (
        '/tmp/glasslab-research-orchestrator/datasets/catalog.json'
    )
    default_evaluation_contract_id: str = 'example-research-v1'
    default_evaluation_contract_version: str = '1.0.0'

    opencode_executable: str = '/usr/local/bin/opencode'
    opencode_server_host: str = '127.0.0.1'
    opencode_start_port: int = 4210
    opencode_start_timeout_seconds: float = 15.0
    opencode_turn_timeout_seconds: float = 1800.0
    opencode_repeated_tool_limit: int = 6
    opencode_structured_repair_attempts: int = 1
    qwen_base_url: str = 'http://192.168.1.17:52415/v1'
    qwen_model_name: str = 'mlx-community/Qwen3-Coder-Next-4bit'
    opencode_runtime_image: str = (
        'ghcr.io/offensivegeneric/glasslab-research-orchestrator:0.1.0'
    )

    cluster_execution_api_url: str = (
        'http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080'
    )
    cluster_execution_mode: str = 'workflow-api'
    cluster_execution_workload_id: str = 'metric-search-v0'
    cluster_execution_experiment_type: str = 'gpu-training-job'
    kubernetes_namespace: str = 'glasslab-v2'
    permitted_job_images: Annotated[list[str], NoDecode] = [
        'ghcr.io/offensivegeneric/glasslab-metric-search:latest',
    ]

    maximum_turns: int = 20
    maximum_methodology_revisions: int = 2
    maximum_runtime_seconds: int = 86400
    maximum_cpu: float = 8.0
    maximum_memory_gib: float = 32.0
    maximum_gpus: int = 1
    maximum_parallel_jobs: int = 4
    one_active_run: bool = True
    job_poll_interval_seconds: float = 10.0
    require_operator_auth: bool = False
    operator_api_token: str | None = None

    discord_enabled: bool = False
    discord_bot_token: str | None = None
    discord_channel_id: str | None = None
    discord_webhook_url: str | None = None
    discord_application_id: str | None = None
    discord_guild_id: str | None = None
    discord_controls_enabled: bool = False
    discord_admin_role_id: str | None = None
    discord_admin_user_ids: Annotated[list[str], NoDecode] = []

    @field_validator('permitted_job_images', mode='before')
    @classmethod
    def parse_image_allowlist(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('discord_admin_user_ids', mode='before')
    @classmethod
    def parse_discord_user_allowlist(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
