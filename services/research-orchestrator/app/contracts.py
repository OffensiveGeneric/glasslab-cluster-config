from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .schemas import (
    EvaluationContractDescriptor,
    ExpandedJobSpec,
    ResolvedEvaluationContract,
)


class ContractIntegrityError(ValueError):
    pass


def _safe_contract_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or path.as_posix() in {'', '.'}:
        raise ContractIntegrityError(f'invalid contract-relative path: {value}')
    return path.as_posix()


def compute_contract_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise ContractIntegrityError(f'contract root is not a real directory: {root}')
    digest = sha256()
    files = sorted(
        path
        for path in root.rglob('*')
        if path.is_file() and path.name != 'contract.sha256'
    )
    if not files:
        raise ContractIntegrityError(f'contract has no content: {root}')
    for path in files:
        if path.is_symlink():
            raise ContractIntegrityError(f'contract file cannot be a symlink: {path}')
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, 'big'))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return digest.hexdigest()


class EvaluationContractResolver:
    def __init__(self, contract_root: str) -> None:
        self.contract_root = Path(contract_root).resolve()

    def resolve(self, contract_id: str, version: str) -> ResolvedEvaluationContract:
        root = (self.contract_root / contract_id / version).resolve()
        if not root.is_relative_to(self.contract_root):
            raise ContractIntegrityError('contract path escapes configured root')
        descriptor_path = root / 'contract.json'
        digest_path = root / 'contract.sha256'
        if not descriptor_path.is_file() or not digest_path.is_file():
            raise ContractIntegrityError(
                f'contract is missing descriptor or checksum: {contract_id}@{version}'
            )
        descriptor = EvaluationContractDescriptor.model_validate_json(
            descriptor_path.read_text()
        )
        if descriptor.contract_id != contract_id or descriptor.version != version:
            raise ContractIntegrityError('contract identity does not match its path')
        for field in (
            descriptor.execution_wrapper,
            descriptor.evaluation_entry_point,
            descriptor.expected_input_schema,
            descriptor.expected_output_schema,
        ):
            relative = _safe_contract_relative_path(field)
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ContractIntegrityError(
                    f'contract references a missing or external file: {field}'
                )
        expected = digest_path.read_text().strip().lower()
        actual = compute_contract_digest(root)
        if expected != actual:
            raise ContractIntegrityError(
                f'contract digest mismatch: expected {expected}, got {actual}'
            )
        return ResolvedEvaluationContract(
            descriptor=descriptor,
            digest=actual,
            root_path=str(root),
        )


FORBIDDEN_OVERRIDE_KEYS = {
    'contract',
    'contract_digest',
    'contract_files',
    'contract_id',
    'contract_mount',
    'evaluation_command',
    'evaluation_contract',
    'evaluation_entry_point',
    'evaluator',
    'evaluator_image',
    'expected_input_schema',
    'expected_output_schema',
}


def reject_contract_overrides(value: Any, *, path: str = 'arguments') -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_OVERRIDE_KEYS:
                raise ContractIntegrityError(
                    f'agent job request cannot override evaluation contract at '
                    f'{path}.{key}'
                )
            reject_contract_overrides(child, path=f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_contract_overrides(child, path=f'{path}[{index}]')


def render_read_only_contract_job(
    spec: ExpandedJobSpec,
    contract: ResolvedEvaluationContract,
    *,
    namespace: str,
) -> dict[str, Any]:
    """Render a review artifact; workflow-api remains the submitting authority."""
    descriptor = contract.descriptor
    if spec.evaluation_contract_digest != contract.digest:
        raise ContractIntegrityError('job contract digest does not match resolver')
    if not descriptor.container_image_digest:
        raise ContractIntegrityError(
            'Kubernetes contract rendering requires a digest-pinned contract image'
        )
    if '@sha256:' not in descriptor.container_image_digest:
        raise ContractIntegrityError('contract image must be pinned by digest')
    wrapper_path = f'/evaluation-contract/{descriptor.execution_wrapper}'
    resources = {
        'cpu': str(spec.resources.cpu),
        'memory': f'{spec.resources.memory_gib}Gi',
    }
    if spec.resources.gpus:
        resources['nvidia.com/gpu'] = str(spec.resources.gpus)
    return {
        'apiVersion': 'batch/v1',
        'kind': 'Job',
        'metadata': {
            'name': f'glasslab-{spec.orchestrator_job_id[:20]}',
            'namespace': namespace,
            'labels': {
                'glasslab.io/research-run': spec.run_id,
                'glasslab.io/contract-id': descriptor.contract_id,
                'glasslab.io/contract-version': descriptor.version,
            },
            'annotations': {
                'glasslab.io/contract-digest': contract.digest,
                'glasslab.io/idempotency-key': spec.idempotency_key,
            },
        },
        'spec': {
            'backoffLimit': 0,
            'activeDeadlineSeconds': spec.resources.wallclock_minutes * 60,
            'template': {
                'metadata': {
                    'labels': {
                        'glasslab.io/research-run': spec.run_id,
                    }
                },
                'spec': {
                    'restartPolicy': 'Never',
                    'automountServiceAccountToken': False,
                    'initContainers': [
                        {
                            'name': 'evaluation-contract',
                            'image': descriptor.container_image_digest,
                            'command': [
                                '/bin/sh',
                                '-c',
                                'cp -a /contract/. /contract-copy/',
                            ],
                            'securityContext': {
                                'allowPrivilegeEscalation': False,
                                'readOnlyRootFilesystem': True,
                                'runAsNonRoot': True,
                                'capabilities': {'drop': ['ALL']},
                            },
                            'volumeMounts': [
                                {
                                    'name': 'evaluation-contract',
                                    'mountPath': '/contract-copy',
                                    'readOnly': False,
                                }
                            ],
                        }
                    ],
                    'containers': [
                        {
                            'name': 'experiment',
                            'image': spec.runner_image,
                            'command': [
                                'python',
                                wrapper_path,
                            ],
                            'env': [
                                {
                                    'name': 'GLASSLAB_EXPERIMENT_ENTRYPOINT_JSON',
                                    'value': json.dumps(
                                        ['python3', '-c', 'print("experiment")']
                                    ),
                                },
                                {
                                    'name': 'GLASSLAB_EVALUATION_ENTRY_POINT',
                                    'value': (
                                        f'/evaluation-contract/'
                                        f'{descriptor.evaluation_entry_point}'
                                    ),
                                },
                                {
                                    'name': 'GLASSLAB_EVALUATION_CONTRACT_ID',
                                    'value': descriptor.contract_id,
                                },
                                {
                                    'name': 'GLASSLAB_EVALUATION_CONTRACT_VERSION',
                                    'value': descriptor.version,
                                },
                                {
                                    'name': 'GLASSLAB_EVALUATION_CONTRACT_DIGEST',
                                    'value': contract.digest,
                                },
                            ],
                            'resources': {
                                'requests': resources,
                                'limits': resources,
                            },
                            'securityContext': {
                                'allowPrivilegeEscalation': False,
                                'readOnlyRootFilesystem': True,
                                'runAsNonRoot': True,
                                'capabilities': {'drop': ['ALL']},
                            },
                            'volumeMounts': [
                                {
                                    'name': 'evaluation-contract',
                                    'mountPath': '/evaluation-contract',
                                    'readOnly': True,
                                }
                            ],
                        }
                    ],
                    'volumes': [
                        {
                            'name': 'evaluation-contract',
                            'emptyDir': {},
                        }
                    ],
                },
            },
        },
    }
