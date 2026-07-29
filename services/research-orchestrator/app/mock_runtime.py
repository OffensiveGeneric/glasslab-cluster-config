from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from .opencode_runtime import AgentRuntime, RuntimeSession
from .schemas import (
    AgentName,
    AgentTurnResult,
    Claim,
    EvaluationContractProposal,
    ProducedFile,
    RequestedAction,
    RunState,
    TurnKind,
)


class ScriptedMockRuntime(AgentRuntime):
    """Deterministic local runtime used only by tests and the smoke path."""

    def __init__(self, *, runner_image: str) -> None:
        self.runner_image = runner_image
        self.sessions: dict[tuple[str, AgentName], RuntimeSession] = {}
        self.turn_counts: defaultdict[AgentName, int] = defaultdict(int)
        self.aborted: list[tuple[str, AgentName, str]] = []

    def ensure_session(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
        existing_session_id: str | None,
    ) -> RuntimeSession:
        key = (run_id, agent)
        session = self.sessions.get(key)
        if session is None:
            session = RuntimeSession(
                runtime_id=f'mock-runtime-{agent.value}-{run_id[:8]}',
                session_id=existing_session_id
                or f'mock-session-{agent.value}-{run_id[:8]}',
            )
            self.sessions[key] = session
        return session

    def run_turn(
        self,
        *,
        run_id: str,
        agent: AgentName,
        workspace: Path,
        session_id: str,
        prompt: str,
    ) -> tuple[AgentTurnResult, str | None]:
        self.turn_counts[agent] += 1
        message_id = f'mock-message-{uuid4().hex[:12]}'
        if agent == AgentName.HONEYDEW and 'Draft a concrete program.md' in prompt:
            (workspace / 'program.md').write_text(
                '# Program\n\n'
                '## Hypothesis\n\n'
                'The bounded candidate will pass the immutable evaluator.\n\n'
                '## Controls\n\n'
                '- Fixed evaluation contract\n'
                '- Fixed seed matrix\n'
                '- Required metrics and evaluation artifacts\n\n'
                '## Stopping condition\n\n'
                'Stop after the approved matrix finishes.\n'
            )
            return (
                AgentTurnResult(
                    kind=TurnKind.PROTOCOL_DRAFT,
                    summary='Drafted a bounded protocol.',
                    evaluation_contract_proposal=(
                        EvaluationContractProposal.model_validate(
                            {
                                'evaluator_type': 'example-research-v1',
                                'primary_metric': {
                                    'name': 'score',
                                    'direction': 'maximize',
                                    'minimum_effect': 0.01,
                                },
                                'guardrails': [],
                                'required_artifacts': [
                                    'metrics.json',
                                    'evaluation.json',
                                ],
                                'budget_mode': 'wallclock',
                                'max_wallclock_minutes': 5,
                                'resource_constraints': {
                                    'cpu': 1,
                                    'memory_gib': 1,
                                    'gpus': 0,
                                    'wallclock_minutes': 5,
                                },
                                'rationale': (
                                    'Use the immutable smoke evaluator for '
                                    'the deterministic mock workflow.'
                                ),
                            }
                        )
                    ),
                    claims=[],
                    produced_files=[
                        ProducedFile(path='program.md', purpose='protocol')
                    ],
                    recommended_next_state=RunState.AWAITING_PROTOCOL_APPROVAL,
                    done=True,
                ),
                message_id,
            )
        if agent == AgentName.BEAKER and (
            'Implement the bounded' in prompt
            or 'Revise the implementation' in prompt
        ):
            (workspace / 'experiment.py').write_text(
                'print("bounded mock experiment")\n'
            )
            (workspace / 'configs').mkdir(exist_ok=True)
            (workspace / 'configs' / 'baseline.yaml').write_text(
                'learning_rate: 0.0001\n'
            )
            kind = (
                TurnKind.REVISION
                if 'Revise the implementation' in prompt
                else TurnKind.IMPLEMENTATION_PROPOSAL
            )
            return (
                AgentTurnResult(
                    kind=kind,
                    summary='Implemented and locally checked the bounded candidate.',
                    claims=[
                        Claim(
                            text='The local implementation file exists.',
                            evidence=['git://beaker/experiment.py'],
                        )
                    ],
                    requested_actions=[
                        RequestedAction(
                            type='submit_experiment_matrix',
                            arguments={
                                'base_config': 'configs/baseline.yaml',
                                'variants': [
                                    {
                                        'name': 'baseline',
                                        'overrides': {'learning_rate': 0.0001},
                                    },
                                    {
                                        'name': 'candidate',
                                        'overrides': {'learning_rate': 0.0003},
                                    },
                                ],
                                'seeds': [17],
                                'maximum_parallel_jobs': 2,
                                'runner_image': self.runner_image,
                                'resources': {
                                    'cpu': 1,
                                    'memory_gib': 1,
                                    'gpus': 0,
                                    'wallclock_minutes': 5,
                                },
                                'required_artifacts': ['metrics.json'],
                            },
                            reason='Execute the reviewed bounded matrix.',
                        )
                    ],
                    recommended_next_state=RunState.HONEYDEW_REVIEWING,
                    done=True,
                ),
                message_id,
            )
        if agent == AgentName.HONEYDEW and 'Review Beaker' in prompt:
            return (
                AgentTurnResult(
                    kind=TurnKind.METHODOLOGY_REVIEW,
                    summary='Controls and comparison are acceptable for the smoke test.',
                    claims=[],
                    message_to_other_agent='Proceed with the reviewed matrix.',
                    recommended_next_state=RunState.AWAITING_EXECUTION_APPROVAL,
                    done=True,
                ),
                message_id,
            )
        if agent == AgentName.BEAKER and 'Analyze the authoritative' in prompt:
            return (
                AgentTurnResult(
                    kind=TurnKind.EXPERIMENT_ANALYSIS,
                    summary='The fake jobs completed and emitted metrics.',
                    claims=[
                        Claim(
                            text='The fake jobs emitted metrics.',
                            evidence=['artifact://fake/metrics.json'],
                        )
                    ],
                    recommended_next_state=RunState.HONEYDEW_VERIFYING,
                    done=True,
                ),
                message_id,
            )
        if agent == AgentName.HONEYDEW and 'Independently verify' in prompt:
            return (
                AgentTurnResult(
                    kind=TurnKind.VERIFICATION,
                    summary='The authoritative fake artifacts support a report.',
                    claims=[
                        Claim(
                            text='The job evidence is internally consistent.',
                            evidence=['event://job.completed'],
                        )
                    ],
                    recommended_next_state=RunState.HONEYDEW_WRITING_REPORT,
                    done=True,
                ),
                message_id,
            )
        if agent == AgentName.HONEYDEW and 'Write report.md' in prompt:
            (workspace / 'report.md').write_text(
                '# Report\n\n'
                'The mock workflow completed. This demonstrates orchestration '
                'behavior only and is not scientific evidence from a real GPU run.\n'
            )
            return (
                AgentTurnResult(
                    kind=TurnKind.FINAL_REPORT,
                    summary='Prepared the evidence-bounded report.',
                    claims=[
                        Claim(
                            text='The mock workflow reached report generation.',
                            evidence=['event://report.created'],
                        )
                    ],
                    produced_files=[
                        ProducedFile(path='report.md', purpose='report')
                    ],
                    recommended_next_state=RunState.AWAITING_FINAL_ACCEPTANCE,
                    done=True,
                ),
                message_id,
            )
        raise AssertionError(
            f'unexpected mock turn for {agent.value}: {prompt[:120]}'
        )

    def abort(self, *, run_id: str, agent: AgentName, session_id: str) -> None:
        self.aborted.append((run_id, agent, session_id))
