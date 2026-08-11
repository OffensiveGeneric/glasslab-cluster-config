"""State-machine transition legality and core schema validation.

Covers the allowed run-state edges and that invalid or terminal-state
transitions raise InvalidTransition, plus strict validation of structured
agent output (evidence must be artifact URIs), evaluation-contract proposal
budget limits, and comma-separated environment allowlists.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AgentTurnResult, EvaluationContractProposal, RunState
from app.state_machine import InvalidTransition, validate_transition


def test_valid_and_invalid_state_transitions() -> None:
    validate_transition(RunState.CREATED, RunState.PREPARING)
    validate_transition(
        RunState.HONEYDEW_REVIEWING,
        RunState.AWAITING_EXECUTION_APPROVAL,
    )
    validate_transition(
        RunState.BEAKER_IMPLEMENTING,
        RunState.BEAKER_REVISING,
    )
    validate_transition(
        RunState.BEAKER_IMPLEMENTING,
        RunState.BEAKER_FINALIZING,
    )
    validate_transition(
        RunState.BEAKER_FINALIZING,
        RunState.HONEYDEW_REVIEWING,
    )
    validate_transition(
        RunState.AWAITING_PROTOCOL_APPROVAL,
        RunState.HONEYDEW_DRAFTING_PROTOCOL,
    )
    validate_transition(
        RunState.AWAITING_PROTOCOL_APPROVAL,
        RunState.BEAKER_DRAFTING_CONTRACT,
    )
    validate_transition(
        RunState.AWAITING_CONTRACT_PROMOTION,
        RunState.BEAKER_PLANNING,
    )
    validate_transition(RunState.BEAKER_PLANNING, RunState.BEAKER_IMPLEMENTING)
    validate_transition(RunState.PAUSED, RunState.CANCELLED)
    with pytest.raises(InvalidTransition):
        validate_transition(RunState.CREATED, RunState.COMPLETE)
    with pytest.raises(InvalidTransition):
        validate_transition(RunState.PAUSED, RunState.COMPLETE)
    with pytest.raises(InvalidTransition):
        validate_transition(RunState.COMPLETE, RunState.PREPARING)


def test_structured_agent_output_validation() -> None:
    # Agent claims must cite durable artifact URIs; a bare prose URL is
    # rejected because prose is not evidence (see AGENTS.md boundaries).
    valid = AgentTurnResult.model_validate(
        {
            'kind': 'verification',
            'summary': 'Verified from authoritative evidence.',
            'claims': [
                {
                    'text': 'The artifact exists.',
                    'evidence': ['artifact://run/metrics.json'],
                }
            ],
            'requested_actions': [],
            'produced_files': [],
            'message_to_other_agent': '',
            'recommended_next_state': 'HONEYDEW_WRITING_REPORT',
            'done': True,
        }
    )
    assert valid.done is True
    with pytest.raises(ValidationError):
        AgentTurnResult.model_validate(
            {
                'kind': 'verification',
                'summary': 'Unsupported evidence.',
                'claims': [
                    {
                        'text': 'Trust me.',
                        'evidence': ['https://example.invalid/prose'],
                    }
                ],
                'done': True,
            }
        )


def test_evaluation_contract_proposal_requires_matching_budget_limit() -> None:
    # budget_mode='training_exposure' demands a max_samples_seen limit; the
    # proposal is invalid without it, forcing an explicit sample budget.
    proposal = {
        'evaluator_type': 'cifar100-unseen-v1',
        'primary_metric': {
            'name': 'test_unseen_global_recall_at_1',
            'direction': 'maximize',
            'minimum_effect': 0.02,
        },
        'guardrails': [],
        'required_artifacts': ['metrics.json', 'evaluation.json'],
        'budget_mode': 'training_exposure',
        'resource_constraints': {
            'cpu': 4,
            'memory_gib': 16,
            'gpus': 1,
            'wallclock_minutes': 60,
        },
        'rationale': 'Compare methods under equal training exposure.',
    }
    with pytest.raises(ValidationError, match='matching limit'):
        EvaluationContractProposal.model_validate(proposal)

    valid = EvaluationContractProposal.model_validate(
        {**proposal, 'max_samples_seen': 500_000}
    )
    assert valid.primary_metric.direction == 'maximize'


def test_comma_separated_image_allowlist_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        'GLASSLAB_ORCHESTRATOR_PERMITTED_JOB_IMAGES',
        'ghcr.io/example/runner:a,ghcr.io/example/runner:b',
    )

    assert Settings().permitted_job_images == [
        'ghcr.io/example/runner:a',
        'ghcr.io/example/runner:b',
    ]
