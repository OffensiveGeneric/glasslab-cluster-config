from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import AgentTurnResult, RunState
from app.state_machine import InvalidTransition, validate_transition


def test_valid_and_invalid_state_transitions() -> None:
    validate_transition(RunState.CREATED, RunState.PREPARING)
    validate_transition(
        RunState.HONEYDEW_REVIEWING,
        RunState.AWAITING_EXECUTION_APPROVAL,
    )
    with pytest.raises(InvalidTransition):
        validate_transition(RunState.CREATED, RunState.COMPLETE)
    with pytest.raises(InvalidTransition):
        validate_transition(RunState.COMPLETE, RunState.PREPARING)


def test_structured_agent_output_validation() -> None:
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
