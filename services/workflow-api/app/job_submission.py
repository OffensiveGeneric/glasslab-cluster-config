from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import re

from typing import Any

from services.common.schemas import RunManifest, RunStatus

from .config import Settings
from .schemas import JobSubmissionReceipt, LogEntry, RunRecord


def workflow_submission_ready(workflow: RunManifest | Any) -> tuple[bool, list[str]]:
    blockers = list(getattr(workflow, 'execution_blockers', []) or [])
    execution_status = str(getattr(workflow, 'execution_status', 'ready')).strip()
    submission_backend = str(getattr(workflow, 'submission_backend', 'unimplemented')).strip()

    if execution_status != 'ready':
        blockers.append(f'workflow execution_status is {execution_status}')
    if submission_backend != 'kubernetes':
        blockers.append(f'workflow submission_backend is {submission_backend}')

    return (not blockers, blockers)


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
    if manifest.workflow_id == 'generic-tabular-benchmark':
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

    if manifest.workflow_id == 'literature-to-experiment':
        paper_id = str(manifest.inputs.get('paper_id', '')).strip()
        source_notes = str(manifest.inputs.get('source_notes', '')).strip()
        dataset_uri = str(manifest.inputs.get('dataset_uri', '')).strip()
        if not paper_id:
            raise ValueError('literature-to-experiment requires paper_id for runner submission')
        if not source_notes:
            raise ValueError('literature-to-experiment requires source_notes for runner submission')
        if not dataset_uri:
            raise ValueError('literature-to-experiment requires dataset_uri for runner submission')

        return {
            'pipeline': 'literature_to_experiment',
            'dataset': dataset_uri,
            'paper_id': paper_id,
            'source_notes': source_notes,
            'dataset_uri': dataset_uri,
            'models': manifest.requested_models,
            'feature_profile': 'basic',
            'resource_profile': manifest.resource_profile,
            'compare_to': 'none',
            'produce_submission': False,
        }

    if manifest.workflow_id == 'gpu-neural-net-experiment':
        dataset_uri = str(manifest.inputs.get('dataset_uri', '')).strip()
        model_family = str(manifest.inputs.get('model_family', '')).strip()
        training_notes = str(manifest.inputs.get('training_notes', '')).strip()
        if not dataset_uri:
            raise ValueError('gpu-neural-net-experiment requires dataset_uri for runner submission')
        if not model_family:
            raise ValueError('gpu-neural-net-experiment requires model_family for runner submission')
        if not training_notes:
            raise ValueError('gpu-neural-net-experiment requires training_notes for runner submission')

        return {
            'pipeline': 'gpu_experiment',
            'dataset': dataset_uri,
            'dataset_uri': dataset_uri,
            'model_family': model_family,
            'training_notes': training_notes,
            'models': manifest.requested_models,
            'feature_profile': 'gpu_ml',
            'resource_profile': manifest.resource_profile,
            'compare_to': 'baseline',
            'produce_submission': False,
        }

    raise ValueError(f'workflow job submission is not implemented yet for {manifest.workflow_id}')


def validate_workflow_submission_support(workflow: Any) -> list[str]:
    _, blockers = workflow_submission_ready(workflow)
    if blockers:
        return blockers

    placeholder_inputs: dict[str, Any] = {}
    for input_spec in getattr(workflow, 'required_inputs', []) or []:
        input_type = getattr(input_spec, 'input_type', 'text')
        name = getattr(input_spec, 'name', 'input')
        if input_type in {'dataset', 'url'}:
            placeholder_inputs[name] = f's3://placeholder/{name}'
        elif input_type == 'notes':
            placeholder_inputs[name] = f'placeholder {name} notes'
        elif input_type == 'parameter_set':
            placeholder_inputs[name] = f'placeholder_{name}'
        else:
            placeholder_inputs[name] = f'placeholder-{name}'

    try:
        manifest = RunManifest(
            run_id='preflight-dry-run',
            workflow_id=workflow.workflow_id,
            workflow_family=workflow.workflow_family,
            display_name=workflow.display_name,
            objective='dry-run submission validation',
            submitted_by='workflow-api-preflight',
            submitted_at=datetime.now(timezone.utc),
            run_priority='user',
            inputs=placeholder_inputs,
            requested_models=list(workflow.allowed_models[:1]),
            resource_profile=workflow.resource_profile.profile_name,
            resource_requests=workflow.resource_profile.requests,
            resource_limits=workflow.resource_profile.limits,
            node_selector=workflow.resource_profile.node_selector,
            runner_image=workflow.runner_image,
            evaluator_type=workflow.evaluator_type,
            approval_tier=workflow.approval_tier,
            expected_artifacts=workflow.expected_artifacts.model_dump(mode='json'),
        )
        _build_runner_spec(manifest)
    except Exception as exc:
        blockers.append(f'workflow submission contract is not implemented: {exc}')
    return blockers


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
            'glasslab.io/run-priority': manifest.run_priority,
        }

        priority_class_name = ''
        if manifest.run_priority == 'autonomous':
            priority_class_name = self.settings.autonomous_priority_class_name
        else:
            priority_class_name = self.settings.user_priority_class_name

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
            resources=self.client.V1ResourceRequirements(
                requests=manifest.resource_requests or None,
                limits=manifest.resource_limits or None,
            ),
        )

        runtime_class_name = None
        requested_gpu = manifest.resource_requests.get('nvidia.com/gpu') or manifest.resource_limits.get('nvidia.com/gpu')
        if requested_gpu:
            runtime_class_name = self.settings.gpu_runtime_class_name

        pod_spec = self.client.V1PodSpec(
            restart_policy='Never',
            service_account_name=self.settings.runner_service_account_name,
            image_pull_secrets=[self.client.V1LocalObjectReference(name=self.settings.image_pull_secret_name)],
            containers=[container],
            priority_class_name=priority_class_name or None,
            runtime_class_name=runtime_class_name,
            node_selector=manifest.node_selector or None,
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
