from __future__ import annotations

from hashlib import sha256

from pydantic import ValidationError

from .contracts import ContractIntegrityError, reject_contract_overrides
from .matrix import canonical_json
from .schemas import (
    ActionRecord,
    AgentName,
    ApprovalStatus,
    ExperimentMatrix,
    PolicyClassification,
    RequestedAction,
)


class ActionPolicy:
    AUTOMATIC_ACTIONS = {
        'read_workspace',
        'edit_workspace',
        'run_local_tests',
        'commit_experiment_branch',
    }
    HUMAN_ACTIONS = {
        'approve_protocol',
        'accept_final_report',
        'push_git_branch',
        'open_pull_request',
        'publish_report',
        'publish_external_artifact',
    }
    DENIED_ACTIONS = {
        'modify_evaluation_contract',
        'read_secrets',
        'delete_namespace',
        'delete_shared_resources',
        'raw_kubectl',
        'unrestricted_ssh',
        'registry_publish',
    }

    def __init__(
        self,
        *,
        permitted_images: list[str],
        maximum_cpu: float,
        maximum_memory_gib: float,
        maximum_gpus: int,
        maximum_parallel_jobs: int,
    ) -> None:
        self.permitted_images = set(permitted_images)
        self.maximum_cpu = maximum_cpu
        self.maximum_memory_gib = maximum_memory_gib
        self.maximum_gpus = maximum_gpus
        self.maximum_parallel_jobs = maximum_parallel_jobs

    def classify(
        self,
        *,
        proposed_by: AgentName,
        action: RequestedAction,
    ) -> PolicyClassification:
        if action.type in self.DENIED_ACTIONS:
            return PolicyClassification.DENY
        try:
            reject_contract_overrides(action.arguments)
        except ContractIntegrityError:
            return PolicyClassification.DENY
        if action.type in self.AUTOMATIC_ACTIONS:
            return PolicyClassification.AUTOMATIC
        if action.type == 'draft_protocol':
            return (
                PolicyClassification.AUTOMATIC
                if proposed_by == AgentName.HONEYDEW
                else PolicyClassification.DENY
            )
        if action.type == 'submit_validation_job':
            return PolicyClassification.HONEYDEW_APPROVAL
        if action.type == 'submit_experiment_matrix':
            try:
                matrix = ExperimentMatrix.model_validate(action.arguments)
            except ValidationError:
                return PolicyClassification.DENY
            if matrix.runner_image not in self.permitted_images:
                return PolicyClassification.DENY
            resources = matrix.resources
            if (
                resources.cpu > self.maximum_cpu
                or resources.memory_gib > self.maximum_memory_gib
                or resources.gpus > self.maximum_gpus
                or matrix.maximum_parallel_jobs > self.maximum_parallel_jobs
            ):
                return PolicyClassification.DENY
            return PolicyClassification.HONEYDEW_AND_HUMAN_APPROVAL
        if action.type in self.HUMAN_ACTIONS:
            return PolicyClassification.HUMAN_APPROVAL
        return PolicyClassification.DENY

    def build_record(
        self,
        *,
        run_id: str,
        proposed_by: AgentName,
        action: RequestedAction,
        ordinal: int,
    ) -> ActionRecord:
        classification = self.classify(
            proposed_by=proposed_by,
            action=action,
        )
        status = (
            ApprovalStatus.AUTOMATICALLY_APPROVED
            if classification == PolicyClassification.AUTOMATIC
            else ApprovalStatus.DENIED
            if classification == PolicyClassification.DENY
            else ApprovalStatus.PENDING
        )
        idempotency_key = sha256(
            canonical_json(
                {
                    'run_id': run_id,
                    'proposed_by': proposed_by.value,
                    'type': action.type,
                    'arguments': action.arguments,
                    'ordinal': ordinal,
                }
            ).encode()
        ).hexdigest()
        return ActionRecord(
            run_id=run_id,
            proposed_by=proposed_by,
            type=action.type,
            arguments=action.arguments,
            policy_classification=classification,
            approval_status=status,
            reason=action.reason,
            idempotency_key=idempotency_key,
        )
