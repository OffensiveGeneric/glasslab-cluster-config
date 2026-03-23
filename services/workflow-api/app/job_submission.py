from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import re

from typing import Any

from services.common.schemas import RunManifest, RunStatus

from .config import Settings
from .schemas import JobSubmissionReceipt, LogEntry, RunRecord


class JobSubmitter(ABC):
    @abstractmethod
    def submit_run(self, manifest: RunManifest) -> JobSubmissionReceipt:
        raise NotImplementedError

    def get_live_status(self, record: RunRecord) -> RunStatus | None:
        return None

    def get_live_logs(self, record: RunRecord) -> list[LogEntry]:
        return []


class NullJobSubmitter(JobSubmitter):
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def submit_run(self, manifest: RunManifest) -> JobSubmissionReceipt:
        return JobSubmissionReceipt(
            job_name=f'{manifest.workflow_id}-{manifest.run_id[:8]}',
            namespace=self.namespace,
            accepted_at=datetime.now(timezone.utc),
            status='accepted',
            detail='Job submission interface is present but not wired to Kubernetes yet.',
        )


def _load_kube_modules() -> tuple[Any, Any, type[Exception], type[Exception]]:
    from kubernetes import client as kube_client
    from kubernetes import config as kube_config
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException as KubeConfigException

    return kube_client, kube_config, KubeConfigException, ApiException


def _load_kube_config(kube_config: Any, config_exception: type[Exception]) -> None:
    try:
        kube_config.load_incluster_config()
    except config_exception:
        kube_config.load_kube_config()


def _sanitize_label(value: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9-.]+', '-', value).strip('-').lower()
    return cleaned[:63] or 'run'


def _build_job_name(manifest: RunManifest) -> str:
    prefix = _sanitize_label(manifest.workflow_id).replace('.', '-')
    return f"{prefix}-{manifest.run_id[:8]}"[:63]


def _build_runner_spec(manifest: RunManifest) -> dict:
    if manifest.workflow_id != 'generic-tabular-benchmark':
        raise ValueError(f'workflow job submission is not implemented yet for {manifest.workflow_id}')

    dataset_name = str(manifest.inputs.get('dataset_name', '')).strip()
    if not dataset_name:
        raise ValueError('generic-tabular-benchmark requires dataset_name for runner submission')

    return {
        'pipeline': 'titanic_baseline' if dataset_name == 'titanic' else 'generic_tabular_benchmark',
        'dataset': dataset_name,
        'models': manifest.requested_models,
        'feature_profile': 'basic',
        'resource_profile': manifest.resource_profile,
        'compare_to': 'none',
        'produce_submission': True,
    }


class KubernetesJobSubmitter(JobSubmitter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client, kube_config, config_exception, self.api_exception = _load_kube_modules()
        _load_kube_config(kube_config, config_exception)
        self.batch_api = self.client.BatchV1Api()
        self.core_api = self.client.CoreV1Api()

    def submit_run(self, manifest: RunManifest) -> JobSubmissionReceipt:
        spec = _build_runner_spec(manifest)
        job_name = _build_job_name(manifest)
        labels = {
            'app.kubernetes.io/name': 'glasslab-v2-runner',
            'glasslab.io/run-id': manifest.run_id,
            'glasslab.io/workflow-id': _sanitize_label(manifest.workflow_id),
        }

        env = [
            self.client.V1EnvVar(name='GLASSLAB_RUNNER_EXPERIMENT_ID', value=manifest.run_id),
            self.client.V1EnvVar(name='GLASSLAB_RUNNER_TRACE_ID', value=manifest.run_id),
            self.client.V1EnvVar(name='GLASSLAB_RUNNER_SPEC_JSON', value=json.dumps(spec, sort_keys=True)),
            self.client.V1EnvVar(name='GLASSLAB_RUNNER_MANIFEST_JSON', value=manifest.model_dump_json()),
            self.client.V1EnvVar(
                name='GLASSLAB_RUNNER_DATASET_ROOT',
                value=f"{self.settings.dataset_mount_path}/{spec['dataset']}",
            ),
            self.client.V1EnvVar(name='GLASSLAB_RUNNER_ARTIFACTS_ROOT', value=self.settings.artifacts_mount_path),
        ]

        container = self.client.V1Container(
            name='runner',
            image=manifest.runner_image,
            image_pull_policy=self.settings.runner_image_pull_policy,
            env=env,
            resources=self.client.V1ResourceRequirements(),
        )

        pod_spec = self.client.V1PodSpec(
            restart_policy='Never',
            service_account_name=self.settings.runner_service_account_name,
            image_pull_secrets=[self.client.V1LocalObjectReference(name=self.settings.image_pull_secret_name)],
            containers=[container],
            volumes=[
                self.client.V1Volume(
                    name='dataset-volume',
                    persistent_volume_claim=self.client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=self.settings.dataset_pvc_name,
                    ),
                ),
                self.client.V1Volume(
                    name='artifacts-volume',
                    persistent_volume_claim=self.client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=self.settings.artifacts_pvc_name,
                    ),
                ),
            ],
        )

        container.volume_mounts = [
            self.client.V1VolumeMount(
                name='dataset-volume',
                mount_path=self.settings.dataset_mount_path,
                read_only=True,
            ),
            self.client.V1VolumeMount(
                name='artifacts-volume',
                mount_path=self.settings.artifacts_mount_path,
            ),
        ]

        job = self.client.V1Job(
            metadata=self.client.V1ObjectMeta(name=job_name, labels=labels),
            spec=self.client.V1JobSpec(
                backoff_limit=self.settings.runner_backoff_limit,
                ttl_seconds_after_finished=self.settings.runner_job_ttl_seconds,
                template=self.client.V1PodTemplateSpec(
                    metadata=self.client.V1ObjectMeta(labels=labels),
                    spec=pod_spec,
                ),
            ),
        )

        self.batch_api.create_namespaced_job(namespace=self.settings.runner_namespace, body=job)
        return JobSubmissionReceipt(
            job_name=job_name,
            namespace=self.settings.runner_namespace,
            accepted_at=datetime.now(timezone.utc),
            status='submitted',
            detail='Run submitted to Kubernetes Job API.',
        )

    def get_live_status(self, record: RunRecord) -> RunStatus | None:
        try:
            job = self.batch_api.read_namespaced_job(
                name=record.job_submission.job_name,
                namespace=record.job_submission.namespace,
            )
        except self.api_exception:
            return None

        now = datetime.now(timezone.utc)
        status = job.status
        detail = None
        if status.conditions:
            detail = '; '.join(filter(None, [condition.message for condition in status.conditions])) or None
        if status.succeeded:
            return RunStatus(run_id=record.run_id, status='succeeded', updated_at=now, detail=detail or 'Kubernetes Job completed successfully.')
        if status.failed:
            return RunStatus(run_id=record.run_id, status='failed', updated_at=now, detail=detail or 'Kubernetes Job reported failure.')
        if status.active:
            return RunStatus(run_id=record.run_id, status='running', updated_at=now, detail='Kubernetes Job is active.')
        return RunStatus(run_id=record.run_id, status='queued', updated_at=now, detail='Kubernetes Job is queued.')

    def get_live_logs(self, record: RunRecord) -> list[LogEntry]:
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=record.job_submission.namespace,
                label_selector=f'job-name={record.job_submission.job_name}',
            )
        except self.api_exception:
            return []

        entries: list[LogEntry] = []
        for pod in pods.items:
            try:
                raw_log = self.core_api.read_namespaced_pod_log(
                    name=pod.metadata.name,
                    namespace=record.job_submission.namespace,
                )
            except self.api_exception:
                continue
            for line in raw_log.splitlines():
                if not line.strip():
                    continue
                entries.append(
                    LogEntry(
                        timestamp=datetime.now(timezone.utc),
                        level='INFO',
                        message=line,
                        payload={'pod_name': pod.metadata.name},
                    )
                )
        return entries


def create_job_submitter(settings: Settings) -> JobSubmitter:
    if settings.job_submission_mode == 'kubernetes':
        return KubernetesJobSubmitter(settings)
    return NullJobSubmitter(namespace=settings.runner_namespace)
