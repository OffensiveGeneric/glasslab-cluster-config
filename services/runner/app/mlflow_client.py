from __future__ import annotations

from contextlib import contextmanager


class MlflowRunLogger:
    def __init__(self, enabled: bool, tracking_uri: str, experiment_name: str):
        self.enabled = enabled and bool(tracking_uri)
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        self._mlflow = None

        if not self.enabled:
            return

        try:
            import mlflow
        except ImportError:
            self.enabled = False
            return

        self._mlflow = mlflow
        self._mlflow.set_tracking_uri(tracking_uri)
        self._mlflow.set_experiment(experiment_name)

    @contextmanager
    def start_run(self, run_name: str):
        if not self.enabled or self._mlflow is None:
            yield self
            return
        with self._mlflow.start_run(run_name=run_name):
            yield self

    def log_params(self, params: dict) -> None:
        if self.enabled and self._mlflow is not None:
            self._mlflow.log_params(params)

    def log_metric(self, name: str, value: float) -> None:
        if self.enabled and self._mlflow is not None:
            self._mlflow.log_metric(name, value)

    def log_artifact(self, path: str) -> None:
        if self.enabled and self._mlflow is not None:
            self._mlflow.log_artifact(path)
