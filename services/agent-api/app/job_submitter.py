from __future__ import annotations

import json
import re
from dataclasses import dataclass

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from .config import Settings
from .mlflow_client import build_runner_mlflow_env
from .registry import DATASET_REGISTRY, RESOURCE_PROFILE_REGISTRY
from .schemas import PlannerSpec


@dataclass
class JobSubmissionResult:
    job_name: str
    namespace: str
    manifest_name: str


def _load_kube_config() -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()


class JobSubmitter:
    def __init__(self, settings: Settings):
        self.settings = settings
        _load_kube_config()
        self.batch_api = client.BatchV1Api()

    def submit_job(self, spec: PlannerSpec, experiment_id: str, trace_id: str) -> JobSubmissionResult:
        profile = RESOURCE_PROFILE_REGISTRY[spec.resource_profile]
        dataset_subpath = DATASET_REGISTRY[spec.dataset]['mount_subpath']
        job_name = _build_job_name(experiment_id)
        labels = {
            'app.kubernetes.io/name': 'glasslab-titanic-runner',
            'glasslab.io/experiment-id': experiment_id,
            'glasslab.io/pipeline': spec.pipeline,
            'glasslab.io/trace-id': _sanitize_label(trace_id),
        }

        env = [
            client.V1EnvVar(name='GLASSLAB_RUNNER_EXPERIMENT_ID', value=experiment_id),
            client.V1EnvVar(name='GLASSLAB_RUNNER_TRACE_ID', value=trace_id),
            client.V1EnvVar(name='GLASSLAB_RUNNER_SPEC_JSON', value=spec.model_dump_json()),
            client.V1EnvVar(
                name='GLASSLAB_RUNNER_DATASET_ROOT',
                value=f"{self.settings.dataset_mount_path}/{dataset_subpath}",
            ),
            client.V1EnvVar(name='GLASSLAB_RUNNER_ARTIFACTS_ROOT', value=self.settings.artifacts_mount_path),
        ]
        for key, value in build_runner_mlflow_env(self.settings).items():
            env.append(client.V1EnvVar(name=key, value=value))

        container = client.V1Container(
            name='runner',
            image=self.settings.runner_image,
            image_pull_policy=self.settings.runner_image_pull_policy,
            env=env,
            resources=client.V1ResourceRequirements(
                requests=profile['requests'],
                limits=profile['limits'],
            ),
            volume_mounts=[
                client.V1VolumeMount(
                    name='dataset-volume',
                    mount_path=self.settings.dataset_mount_path,
                    read_only=True,
                ),
                client.V1VolumeMount(
                    name='artifacts-volume',
                    mount_path=self.settings.artifacts_mount_path,
                ),
            ],
        )

        pod_spec = client.V1PodSpec(
            restart_policy='Never',
            service_account_name=self.settings.runner_service_account_name,
            containers=[container],
            node_selector=profile['node_selector'],
            runtime_class_name=profile['runtime_class_name'],
            volumes=[
                client.V1Volume(
                    name='dataset-volume',
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=self.settings.dataset_pvc_name,
                    ),
                ),
                client.V1Volume(
                    name='artifacts-volume',
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=self.settings.artifacts_pvc_name,
                    ),
                ),
            ],
        )

        job = client.V1Job(
            metadata=client.V1ObjectMeta(name=job_name, labels=labels),
            spec=client.V1JobSpec(
                backoff_limit=self.settings.runner_backoff_limit,
                ttl_seconds_after_finished=self.settings.runner_job_ttl_seconds,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=labels),
                    spec=pod_spec,
                ),
            ),
        )

        self.batch_api.create_namespaced_job(namespace=self.settings.runner_namespace, body=job)
        return JobSubmissionResult(
            job_name=job_name,
            namespace=self.settings.runner_namespace,
            manifest_name=job.metadata.name,
        )


def _build_job_name(experiment_id: str) -> str:
    return f'titanic-baseline-{experiment_id[:8]}'


def _sanitize_label(value: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9-.]+', '-', value).strip('-').lower()
    return cleaned[:63] or 'trace'
