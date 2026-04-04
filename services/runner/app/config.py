from __future__ import annotations

import json
from copy import deepcopy
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
    manifest_json: str = ''
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
        spec = json.loads(self.spec_json)
        manifest = self.parsed_manifest

        # Prefer the explicit runner spec, but backfill bounded technique context
        # from manifest inputs so scoring survives spec/manifest drift.
        if spec.get('pipeline') == 'gpu_experiment' and isinstance(manifest, dict):
            inputs = manifest.get('inputs', {})
            if isinstance(inputs, dict):
                merged = deepcopy(spec)
                for key in (
                    'technique_candidate_models',
                    'technique_baseline_models',
                    'technique_loss_or_distance',
                    'technique_task_type',
                    'technique_metrics',
                ):
                    if key in inputs and inputs.get(key) not in (None, '', []):
                        merged[key] = inputs[key]
                return merged
        return spec

    @property
    def parsed_manifest(self) -> dict:
        if not self.manifest_json:
            return {}
        return json.loads(self.manifest_json)
