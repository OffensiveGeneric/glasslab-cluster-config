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
    gpu_runtime_class_name: str = 'nvidia'
    user_priority_class_name: str = 'glasslab-user-high'
    autonomous_priority_class_name: str = 'glasslab-autonomous-low'
    intake_agent_enabled: bool = False
    intake_agent_url: str = 'http://glasslab-intake-agent.glasslab-v2.svc.cluster.local:8090'
    intake_agent_timeout_seconds: float = 30.0
    interpretation_agent_enabled: bool = False
    interpretation_agent_url: str = 'http://glasslab-interpretation-agent.glasslab-v2.svc.cluster.local:8091'
    interpretation_agent_timeout_seconds: float = 45.0
    assessment_agent_enabled: bool = False
    assessment_agent_url: str = 'http://glasslab-assessment-agent.glasslab-v2.svc.cluster.local:8092'
    assessment_agent_timeout_seconds: float = 45.0
    design_agent_enabled: bool = False
    design_agent_url: str = 'http://glasslab-design-agent.glasslab-v2.svc.cluster.local:8093'
    design_agent_timeout_seconds: float = 45.0
    ranker_enabled: bool = False
    ranker_url: str = 'http://192.168.1.12:8181/rank/workflow-family'
    ranker_timeout_seconds: float = 15.0
    ranker_min_top_score: float = 0.75
    ranker_min_score_gap: float = 0.10
    source_document_storage_mode: Literal['filesystem', 'minio'] = 'filesystem'
    source_document_storage_dir: str = '/mnt/artifacts/source-documents'
    source_document_bucket: str = 'research-sources'
    minio_endpoint: str = 'glasslab-minio.glasslab-v2.svc.cluster.local:9000'
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_secure: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
