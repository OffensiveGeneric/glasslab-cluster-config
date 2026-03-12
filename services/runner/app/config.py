from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_prefix='GLASSLAB_RUNNER_',
        case_sensitive=False,
        extra='ignore',
    )

    experiment_id: str = 'local-dev'
    trace_id: str = 'local-dev'
    spec_json: str = (
        '{"pipeline":"titanic_baseline","dataset":"titanic","models":["logistic_regression","random_forest"],'
        '"feature_profile":"basic","resource_profile":"cpu-small","compare_to":"none","produce_submission":true}'
    )
    dataset_root: str = '/mnt/datasets/titanic'
    artifacts_root: str = '/mnt/artifacts'
    validation_size: float = 0.25
    random_state: int = 42
    log_level: str = 'INFO'

    mlflow_enabled: bool = False
    mlflow_tracking_uri: str = ''
    mlflow_experiment_name: str = 'glasslab-titanic'

    @property
    def artifact_dir(self) -> Path:
        return Path(self.artifacts_root) / self.experiment_id

    @property
    def parsed_spec(self) -> dict:
        return json.loads(self.spec_json)
