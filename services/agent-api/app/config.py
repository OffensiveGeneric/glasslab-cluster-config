from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix='GLASSLAB_AGENT_',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'glasslab-agent-api'
    app_version: str = '0.1.0'
    log_level: str = 'INFO'

    planner_model_name: str = 'Qwen/Qwen3-4B-Instruct-2507'
    qwen_api_base: str = 'http://vllm.glasslab-agents.svc.cluster.local:8000/v1'
    qwen_api_key: str = 'change-me'
    qwen_timeout_seconds: int = 30
    planner_temperature: float = 0.0
    planner_max_tokens: int = 256
    planner_seed: int = 7
    llm_summary_enabled: bool = True

    runner_namespace: str = 'glasslab-agents'
    runner_service_account_name: str = 'glasslab-agent-api'
    runner_image: str = 'ghcr.io/offensivegeneric/glasslab-titanic-runner:0.1.0'
    runner_image_pull_policy: str = 'IfNotPresent'
    runner_backoff_limit: int = 0
    runner_job_ttl_seconds: int = 86400
    gpu_runtime_class_name: str = 'nvidia'

    dataset_pvc_name: str = 'titanic-datasets'
    dataset_mount_path: str = '/mnt/datasets'
    dataset_subpath_titanic: str = 'titanic'

    artifacts_pvc_name: str = 'glasslab-agent-artifacts'
    artifacts_mount_path: str = '/mnt/artifacts'

    state_pvc_name: str = 'glasslab-agent-state'
    state_mount_path: str = '/var/lib/glasslab-agent/state'
    state_db_path: str = '/var/lib/glasslab-agent/state/agent.db'

    mlflow_tracking_uri: str = ''
    mlflow_enabled: bool = False
    mlflow_experiment_name: str = 'glasslab-titanic'

    poll_interval_seconds: int = 10
    auto_monitor_submitted_jobs: bool = True

    @property
    def titanic_dataset_path(self) -> str:
        return f'{self.dataset_mount_path}/{self.dataset_subpath_titanic}'


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
