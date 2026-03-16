from __future__ import annotations

from functools import lru_cache

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
