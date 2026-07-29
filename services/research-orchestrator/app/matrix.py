from __future__ import annotations

from hashlib import sha256
import json
from uuid import uuid5, NAMESPACE_URL

from .contracts import reject_contract_overrides
from .schemas import (
    ExpandedJobSpec,
    ExperimentMatrix,
    ResolvedEvaluationContract,
)


class MatrixExpansionError(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def expand_experiment_matrix(
    *,
    run_id: str,
    action_id: str,
    matrix: ExperimentMatrix,
    contract: ResolvedEvaluationContract,
) -> list[ExpandedJobSpec]:
    reject_contract_overrides(matrix.model_dump(mode='json'))
    ceiling = contract.descriptor.resource_constraints
    requested = matrix.resources
    if (
        requested.cpu > ceiling.cpu
        or requested.memory_gib > ceiling.memory_gib
        or requested.gpus > ceiling.gpus
        or requested.wallclock_minutes > ceiling.wallclock_minutes
    ):
        raise MatrixExpansionError(
            'experiment matrix exceeds evaluation-contract resource constraints'
        )
    expanded: list[ExpandedJobSpec] = []
    required_artifacts = list(
        dict.fromkeys(
            [
                *contract.descriptor.required_artifacts,
                *matrix.required_artifacts,
            ]
        )
    )
    for variant in matrix.variants:
        for seed in matrix.seeds:
            identity = {
                'run_id': run_id,
                'action_id': action_id,
                'variant': variant.name,
                'seed': seed,
                'base_config': matrix.base_config,
                'overrides': variant.overrides,
                'contract_digest': contract.digest,
            }
            idempotency_key = sha256(canonical_json(identity).encode()).hexdigest()
            expanded.append(
                ExpandedJobSpec(
                    orchestrator_job_id=uuid5(
                        NAMESPACE_URL,
                        f'glasslab-job:{idempotency_key}',
                    ).hex,
                    run_id=run_id,
                    action_id=action_id,
                    variant_name=variant.name,
                    seed=seed,
                    idempotency_key=idempotency_key,
                    base_config=matrix.base_config,
                    overrides=variant.overrides,
                    runner_image=matrix.runner_image,
                    resources=matrix.resources,
                    required_artifacts=required_artifacts,
                    evaluation_contract_id=contract.descriptor.contract_id,
                    evaluation_contract_version=contract.descriptor.version,
                    evaluation_contract_digest=contract.digest,
                )
            )
    return expanded
