from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import discover_repo_root

DEFAULT_REGISTRY_DIR = discover_repo_root() / 'services' / 'workflow-registry' / 'definitions'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix='GLASSLAB_WORKFLOW_API_',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'glasslab-workflow-api'
    app_version: str = '0.1.0'
    log_level: str = 'INFO'
    registry_dir: str = str(DEFAULT_REGISTRY_DIR)
    runner_namespace: str = 'glasslab-v2'
    default_submitted_by: str = 'glasslab-operator'
    job_submission_mode: Literal['null', 'kubernetes'] = 'null'
    runner_service_account_name: str = 'default'
    runner_image_pull_policy: str = 'IfNotPresent'
    runner_backoff_limit: int = 0
    runner_job_ttl_seconds: int = 86400
    dataset_pvc_name: str = 'glasslab-shared-datasets'
    dataset_mount_path: str = '/mnt/datasets'
    artifacts_pvc_name: str = 'glasslab-shared-artifacts'
    artifacts_mount_path: str = '/mnt/artifacts'
    image_pull_secret_name: str = 'glasslab-ghcr-pull'
    intake_agent_enabled: bool = False
    intake_agent_url: str = 'http://glasslab-intake-agent.glasslab-v2.svc.cluster.local:8090'
    intake_agent_timeout_seconds: float = 30.0
    interpretation_agent_enabled: bool = False
    interpretation_agent_url: str = 'http://glasslab-interpretation-agent.glasslab-v2.svc.cluster.local:8091'
    interpretation_agent_timeout_seconds: float = 45.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
