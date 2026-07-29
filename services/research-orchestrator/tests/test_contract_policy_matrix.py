from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest
from pydantic import ValidationError

from app.contracts import (
    ContractIntegrityError,
    EvaluationContractResolver,
    reject_contract_overrides,
    render_read_only_contract_job,
)
from app.matrix import MatrixExpansionError, expand_experiment_matrix
from app.policy import ActionPolicy
from app.schemas import (
    AgentName,
    ExperimentMatrix,
    PolicyClassification,
    RequestedAction,
)

from conftest import RUNNER_IMAGE


def _matrix() -> ExperimentMatrix:
    return ExperimentMatrix.model_validate(
        {
            'base_config': 'configs/baseline.yaml',
            'variants': [
                {'name': 'a', 'overrides': {'learning_rate': 0.1}},
                {'name': 'b', 'overrides': {'learning_rate': 0.2}},
            ],
            'seeds': [17, 31],
            'maximum_parallel_jobs': 2,
            'runner_image': RUNNER_IMAGE,
            'resources': {
                'cpu': 1,
                'memory_gib': 1,
                'gpus': 0,
                'wallclock_minutes': 5,
            },
            'required_artifacts': ['metrics.json'],
        }
    )


def test_action_policy_decisions() -> None:
    policy = ActionPolicy(
        permitted_images=[RUNNER_IMAGE],
        maximum_cpu=4,
        maximum_memory_gib=8,
        maximum_gpus=1,
        maximum_parallel_jobs=2,
    )
    assert policy.classify(
        proposed_by=AgentName.BEAKER,
        action=RequestedAction(
            type='run_local_tests',
            reason='Validate locally.',
        ),
    ) == PolicyClassification.AUTOMATIC
    assert policy.classify(
        proposed_by=AgentName.BEAKER,
        action=RequestedAction(
            type='submit_experiment_matrix',
            arguments=_matrix().model_dump(mode='json'),
            reason='Run reviewed experiments.',
        ),
    ) == PolicyClassification.HONEYDEW_AND_HUMAN_APPROVAL
    assert policy.classify(
        proposed_by=AgentName.BEAKER,
        action=RequestedAction(
            type='raw_kubectl',
            reason='Bypass the control plane.',
        ),
    ) == PolicyClassification.DENY


def test_evaluation_contract_modification_is_rejected(tmp_path, orchestrator_bundle) -> None:
    settings = orchestrator_bundle[0]
    copied = tmp_path / 'contracts'
    shutil.copytree(settings.evaluation_contract_root, copied)
    resolver = EvaluationContractResolver(str(copied))
    resolver.resolve('example-research-v1', '1.0.0')
    evaluator = (
        copied
        / 'example-research-v1'
        / '1.0.0'
        / 'evaluator.py'
    )
    evaluator.write_text(evaluator.read_text() + '\n# unauthorized drift\n')
    with pytest.raises(ContractIntegrityError, match='digest mismatch'):
        resolver.resolve('example-research-v1', '1.0.0')
    with pytest.raises(ContractIntegrityError, match='cannot override'):
        reject_contract_overrides(
            {'overrides': {'evaluation_entry_point': 'attacker.py'}}
        )


def test_job_spec_validation_and_read_only_contract(orchestrator_bundle) -> None:
    settings, _, _, _, engine = orchestrator_bundle
    contract = engine.contracts.resolve('example-research-v1', '1.0.0')
    specs = expand_experiment_matrix(
        run_id='run-1',
        action_id='action-1',
        matrix=_matrix(),
        contract=contract,
    )
    rendered = render_read_only_contract_job(
        specs[0],
        contract,
        namespace=settings.kubernetes_namespace,
    )
    pod = rendered['spec']['template']['spec']
    mount = pod['containers'][0]['volumeMounts'][0]
    assert mount['mountPath'] == '/evaluation-contract'
    assert mount['readOnly'] is True
    assert pod['automountServiceAccountToken'] is False
    assert pod['containers'][0]['command'] == [
        'python',
        '/evaluation-contract/run_contract.py',
    ]
    gpu_matrix = _matrix().model_copy(
        update={
            'resources': _matrix().resources.model_copy(update={'gpus': 1})
        }
    )
    gpu_spec = expand_experiment_matrix(
        run_id='run-gpu',
        action_id='action-gpu',
        matrix=gpu_matrix,
        contract=contract,
    )[0]
    gpu_job = render_read_only_contract_job(
        gpu_spec,
        contract,
        namespace=settings.kubernetes_namespace,
    )
    assert (
        gpu_job['spec']['template']['spec']['containers'][0]['resources']
        ['limits']['nvidia.com/gpu']
        == '1'
    )
    with pytest.raises(ValidationError):
        ExperimentMatrix.model_validate(
            {
                **_matrix().model_dump(mode='json'),
                'evaluation_entry_point': 'attacker.py',
            }
        )


def test_experiment_matrix_expansion_is_deterministic(orchestrator_bundle) -> None:
    engine = orchestrator_bundle[-1]
    contract = engine.contracts.resolve('example-research-v1', '1.0.0')
    first = expand_experiment_matrix(
        run_id='run-1',
        action_id='action-1',
        matrix=_matrix(),
        contract=contract,
    )
    second = expand_experiment_matrix(
        run_id='run-1',
        action_id='action-1',
        matrix=_matrix(),
        contract=contract,
    )
    assert [item.model_dump() for item in first] == [
        item.model_dump() for item in second
    ]
    assert [(item.variant_name, item.seed) for item in first] == [
        ('a', 17),
        ('a', 31),
        ('b', 17),
        ('b', 31),
    ]
    assert len({item.idempotency_key for item in first}) == 4

    oversized = _matrix().model_copy(
        update={
            'resources': _matrix().resources.model_copy(
                update={'wallclock_minutes': 6}
            )
        }
    )
    with pytest.raises(MatrixExpansionError, match='resource constraints'):
        expand_experiment_matrix(
            run_id='run-1',
            action_id='action-oversized',
            matrix=oversized,
            contract=contract,
        )
