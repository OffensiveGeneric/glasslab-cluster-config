from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    approved_repo_path: str = '/workspace/cluster-config'
    approved_repo_ref: str = 'main'
    evaluation_contract_root: str = str(SERVICE_ROOT / 'evaluation-contracts')
    default_evaluation_contract_id: str = 'example-research-v1'
    default_evaluation_contract_version: str = '1.0.0'

    opencode_executable: str = '/usr/local/bin/opencode'
    opencode_server_host: str = '127.0.0.1'
    opencode_start_port: int = 4210
    opencode_start_timeout_seconds: float = 15.0
    opencode_turn_timeout_seconds: float = 900.0
    qwen_base_url: str = 'http://192.168.1.18:52415/v1'
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
    permitted_job_images: list[str] = [
        'ghcr.io/offensivegeneric/glasslab-metric-search:latest',
    ]

    maximum_turns: int = 20
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

    @field_validator('permitted_job_images', mode='before')
    @classmethod
    def parse_image_allowlist(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
