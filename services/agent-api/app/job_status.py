from __future__ import annotations

import json
from pathlib import Path

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from .config import Settings
from .schemas import ArtifactRef


def _load_kube_config() -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()


class JobStatusService:
    def __init__(self, settings: Settings):
        self.settings = settings
        _load_kube_config()
        self.batch_api = client.BatchV1Api()
        self.core_api = client.CoreV1Api()

    def get_job_status(self, job_name: str) -> dict:
        try:
            job = self.batch_api.read_namespaced_job_status(
                name=job_name,
                namespace=self.settings.runner_namespace,
            )
        except ApiException as exc:
            if exc.status == 404:
                return {'job_name': job_name, 'status': 'missing', 'message': 'job not found'}
            raise

        status = job.status
        phase = 'pending'
        if status.succeeded:
            phase = 'succeeded'
        elif status.failed:
            phase = 'failed'
        elif status.active:
            phase = 'running'

        return {
            'job_name': job_name,
            'status': phase,
            'active': status.active or 0,
            'succeeded': status.succeeded or 0,
            'failed': status.failed or 0,
            'start_time': status.start_time.isoformat() if status.start_time else None,
            'completion_time': status.completion_time.isoformat() if status.completion_time else None,
            'conditions': [
                {
                    'type': condition.type,
                    'status': condition.status,
                    'reason': condition.reason,
                    'message': condition.message,
                }
                for condition in (status.conditions or [])
            ],
        }

    def read_failure_message(self, job_name: str) -> str | None:
        pod_names = self.get_pod_names(job_name)
        if not pod_names:
            return None
        pod_name = pod_names[0]
        try:
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.settings.runner_namespace,
                tail_lines=40,
            )
        except ApiException:
            return None
        return logs.strip() or None

    def get_pod_names(self, job_name: str) -> list[str]:
        pods = self.core_api.list_namespaced_pod(
            namespace=self.settings.runner_namespace,
            label_selector=f'job-name={job_name}',
        )
        return [item.metadata.name for item in pods.items]

    def list_artifacts(self, experiment_id: str) -> list[ArtifactRef]:
        root = Path(self.settings.artifacts_mount_path) / experiment_id
        if not root.exists():
            return []
        artifacts: list[ArtifactRef] = []
        for path in sorted(root.rglob('*')):
            if path.is_file():
                artifacts.append(
                    ArtifactRef(
                        name=path.name,
                        path=str(path),
                        size_bytes=path.stat().st_size,
                    )
                )
        return artifacts

    def read_result_payload(self, experiment_id: str) -> dict | None:
        payload_path = Path(self.settings.artifacts_mount_path) / experiment_id / 'result_payload.json'
        if not payload_path.exists():
            return None
        return json.loads(payload_path.read_text())
