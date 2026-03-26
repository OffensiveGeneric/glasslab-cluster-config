from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.common.schemas import WorkflowRegistryEntry

from .config import Settings
from .job_submission import validate_workflow_submission_support
from .job_submission import _load_kube_config, _load_kube_modules
from .schemas import ExecutionPreflightResult


def _parse_cpu(value: str | None) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if text.endswith("m"):
        return int(float(text[:-1] or "0"))
    return int(float(text) * 1000)


def _parse_bytes(value: str | None) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    suffixes = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "Ti": 1024 ** 4,
        "Pi": 1024 ** 5,
        "Ei": 1024 ** 6,
        "K": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3,
        "T": 1000 ** 4,
        "P": 1000 ** 5,
        "E": 1000 ** 6,
    }
    for suffix, scale in suffixes.items():
        if text.endswith(suffix):
            return int(float(text[:-len(suffix)] or "0") * scale)
    return int(float(text))


def _parse_quantity(resource_name: str, value: str | None) -> int:
    name = resource_name.strip().lower()
    if name == "cpu":
        return _parse_cpu(value)
    if name in {"memory", "ephemeral-storage"} or name.startswith("hugepages-"):
        return _parse_bytes(value)
    return int(float(str(value or "0").strip() or "0"))


def build_execution_preflight_result(workflow: WorkflowRegistryEntry, settings: Settings) -> ExecutionPreflightResult:
    warnings: list[str] = []
    blocking_issues: list[str] = list(workflow.execution_blockers)
    resource_requests = dict(workflow.resource_profile.requests)
    resource_limits = dict(workflow.resource_profile.limits)
    node_selector = dict(workflow.resource_profile.node_selector)

    if not workflow.runner_image.strip():
        blocking_issues.append("workflow registry entry is missing runner_image")

    submission_blockers = validate_workflow_submission_support(workflow)
    for blocker in submission_blockers:
        if blocker not in blocking_issues:
            blocking_issues.append(blocker)

    if settings.job_submission_mode != "kubernetes":
        warnings.append("job submission mode is not kubernetes; live cluster preflight was skipped")
        return ExecutionPreflightResult(
            workflow_id=workflow.workflow_id,
            runner_image=workflow.runner_image,
            resource_profile=workflow.resource_profile.profile_name,
            resource_requests=resource_requests,
            resource_limits=resource_limits,
            node_selector=node_selector,
            job_submission_mode=settings.job_submission_mode,
            execution_status=workflow.execution_status,
            submission_backend=workflow.submission_backend,
            ready=not blocking_issues,
            eligible_nodes=[],
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

    try:
        kube_client, kube_config, config_exception, api_exception = _load_kube_modules()
        _load_kube_config(kube_config, config_exception)
        core_api = kube_client.CoreV1Api()
    except Exception as exc:  # pragma: no cover - environment dependent
        blocking_issues.append(f"failed to initialize Kubernetes client for preflight: {exc}")
        return ExecutionPreflightResult(
            workflow_id=workflow.workflow_id,
            runner_image=workflow.runner_image,
            resource_profile=workflow.resource_profile.profile_name,
            resource_requests=resource_requests,
            resource_limits=resource_limits,
            node_selector=node_selector,
            job_submission_mode=settings.job_submission_mode,
            execution_status=workflow.execution_status,
            submission_backend=workflow.submission_backend,
            ready=False,
            eligible_nodes=[],
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

    try:
        dataset_pvc = core_api.read_namespaced_persistent_volume_claim(
            name=settings.dataset_pvc_name,
            namespace=settings.runner_namespace,
        )
        if dataset_pvc.status.phase != "Bound":
            blocking_issues.append(
                f"dataset PVC {settings.dataset_pvc_name} is not Bound (phase={dataset_pvc.status.phase})"
            )
    except api_exception:
        blocking_issues.append(f"dataset PVC {settings.dataset_pvc_name} not found in namespace {settings.runner_namespace}")

    try:
        artifacts_pvc = core_api.read_namespaced_persistent_volume_claim(
            name=settings.artifacts_pvc_name,
            namespace=settings.runner_namespace,
        )
        if artifacts_pvc.status.phase != "Bound":
            blocking_issues.append(
                f"artifacts PVC {settings.artifacts_pvc_name} is not Bound (phase={artifacts_pvc.status.phase})"
            )
    except api_exception:
        blocking_issues.append(f"artifacts PVC {settings.artifacts_pvc_name} not found in namespace {settings.runner_namespace}")

    try:
        core_api.read_namespaced_secret(
            name=settings.image_pull_secret_name,
            namespace=settings.runner_namespace,
        )
    except api_exception:
        blocking_issues.append(
            f"image pull secret {settings.image_pull_secret_name} not found in namespace {settings.runner_namespace}"
        )

    try:
        nodes = core_api.list_node().items
        pods = core_api.list_pod_for_all_namespaces().items
    except api_exception as exc:
        blocking_issues.append(f"failed to inspect cluster state for preflight: {exc}")
        return ExecutionPreflightResult(
            workflow_id=workflow.workflow_id,
            runner_image=workflow.runner_image,
            resource_profile=workflow.resource_profile.profile_name,
            resource_requests=resource_requests,
            resource_limits=resource_limits,
            node_selector=node_selector,
            job_submission_mode=settings.job_submission_mode,
            execution_status=workflow.execution_status,
            submission_backend=workflow.submission_backend,
            ready=False,
            eligible_nodes=[],
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

    allocated: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for pod in pods:
        if pod.status.phase in {"Succeeded", "Failed"}:
            continue
        node_name = pod.spec.node_name
        if not node_name:
            continue
        for container in pod.spec.containers:
            requests = container.resources.requests or {}
            for resource_name, value in requests.items():
                allocated[node_name][resource_name] += _parse_quantity(resource_name, value)

    eligible_nodes: list[str] = []
    requested_quantities = {
        resource_name: _parse_quantity(resource_name, value)
        for resource_name, value in resource_requests.items()
    }

    for node in nodes:
        if not any(condition.type == "Ready" and condition.status == "True" for condition in node.status.conditions or []):
            continue
        labels = node.metadata.labels or {}
        if any(labels.get(key) != value for key, value in node_selector.items()):
            continue

        fits = True
        for resource_name, requested_quantity in requested_quantities.items():
            allocatable_quantity = _parse_quantity(
                resource_name,
                (node.status.allocatable or {}).get(resource_name, "0"),
            )
            available_quantity = allocatable_quantity - allocated[node.metadata.name].get(resource_name, 0)
            if available_quantity < requested_quantity:
                fits = False
                break
        if fits:
            eligible_nodes.append(node.metadata.name)

    if not eligible_nodes:
        blocking_issues.append(
            "no Ready node currently satisfies the requested resource profile and node selector"
        )

    if "ephemeral-storage" not in resource_requests:
        warnings.append("ephemeral-storage is not declared in the workflow resource profile")
    warnings.append("package prerequisites are assumed to be baked into the declared runner_image; image contents are not yet introspected during preflight")

    return ExecutionPreflightResult(
        workflow_id=workflow.workflow_id,
        runner_image=workflow.runner_image,
        resource_profile=workflow.resource_profile.profile_name,
        resource_requests=resource_requests,
        resource_limits=resource_limits,
        node_selector=node_selector,
        job_submission_mode=settings.job_submission_mode,
        execution_status=workflow.execution_status,
        submission_backend=workflow.submission_backend,
        ready=not blocking_issues,
        eligible_nodes=eligible_nodes,
        blocking_issues=blocking_issues,
        warnings=warnings,
    )
