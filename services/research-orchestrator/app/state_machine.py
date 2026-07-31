from __future__ import annotations

from .schemas import RunState, TERMINAL_STATES


TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.CREATED: {RunState.PREPARING, RunState.CANCELLED, RunState.FAILED},
    RunState.PREPARING: {
        RunState.HONEYDEW_DRAFTING_PROTOCOL,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
    },
    RunState.HONEYDEW_DRAFTING_PROTOCOL: {
        RunState.AWAITING_PROTOCOL_APPROVAL,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.AWAITING_PROTOCOL_APPROVAL: {
        RunState.HONEYDEW_DRAFTING_PROTOCOL,
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.BEAKER_PLANNING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.BEAKER_DRAFTING_CONTRACT: {
        RunState.HONEYDEW_REVIEWING_CONTRACT,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.HONEYDEW_REVIEWING_CONTRACT: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.AWAITING_CONTRACT_PROMOTION,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.AWAITING_CONTRACT_PROMOTION: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.BEAKER_PLANNING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.BEAKER_PLANNING: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.BEAKER_IMPLEMENTING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.BEAKER_IMPLEMENTING: {
        RunState.BEAKER_PLANNING,
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.BEAKER_FINALIZING,
        RunState.BEAKER_REVISING,
        RunState.HONEYDEW_REVIEWING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.BEAKER_FINALIZING: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.BEAKER_REVISING,
        RunState.HONEYDEW_REVIEWING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.HONEYDEW_REVIEWING: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.BEAKER_REVISING,
        RunState.AWAITING_EXECUTION_APPROVAL,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.BEAKER_REVISING: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.HONEYDEW_REVIEWING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.AWAITING_EXECUTION_APPROVAL: {
        RunState.BEAKER_DRAFTING_CONTRACT,
        RunState.JOB_QUEUED,
        RunState.BEAKER_REVISING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.JOB_QUEUED: {
        RunState.JOB_RUNNING,
        RunState.BEAKER_ANALYZING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.JOB_RUNNING: {
        RunState.BEAKER_ANALYZING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.BEAKER_ANALYZING: {
        RunState.HONEYDEW_VERIFYING,
        RunState.BEAKER_REVISING,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.HONEYDEW_VERIFYING: {
        RunState.BEAKER_REVISING,
        RunState.HONEYDEW_WRITING_REPORT,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.HONEYDEW_WRITING_REPORT: {
        RunState.AWAITING_FINAL_ACCEPTANCE,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.AWAITING_FINAL_ACCEPTANCE: {
        RunState.COMPLETE,
        RunState.HONEYDEW_WRITING_REPORT,
        RunState.PAUSED,
        RunState.CANCELLED,
        RunState.FAILED,
        RunState.TIMED_OUT,
    },
    RunState.PAUSED: set(RunState) - TERMINAL_STATES - {RunState.PAUSED},
    RunState.COMPLETE: set(),
    RunState.FAILED: set(),
    RunState.CANCELLED: set(),
    RunState.TIMED_OUT: set(),
}


class InvalidTransition(ValueError):
    pass


def validate_transition(current: RunState, target: RunState) -> None:
    if target not in TRANSITIONS[current]:
        raise InvalidTransition(f'invalid run transition: {current} -> {target}')
