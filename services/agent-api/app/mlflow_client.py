"""Project the API's MLflow settings into the runner's environment.

The runner performs the actual logging inside the cluster; the API only passes
the tracking URI and experiment name through as GLASSLAB_RUNNER_MLFLOW_* vars,
and disables logging entirely when mlflow_enabled is false. mlflow_status_payload
exists for observability endpoints.
"""

from __future__ import annotations

from .config import Settings


def build_runner_mlflow_env(settings: Settings) -> dict[str, str]:
    return {
        'GLASSLAB_RUNNER_MLFLOW_ENABLED': 'true' if settings.mlflow_enabled else 'false',
        'GLASSLAB_RUNNER_MLFLOW_TRACKING_URI': settings.mlflow_tracking_uri,
        'GLASSLAB_RUNNER_MLFLOW_EXPERIMENT_NAME': settings.mlflow_experiment_name,
    }


def mlflow_status_payload(settings: Settings) -> dict[str, str | bool]:
    return {
        'enabled': settings.mlflow_enabled,
        'tracking_uri': settings.mlflow_tracking_uri,
        'experiment_name': settings.mlflow_experiment_name,
    }
