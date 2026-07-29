from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4, uuid5, NAMESPACE_URL

from .cluster import ClusterExecutor
from .config import Settings
from .contracts import EvaluationContractResolver
from .discord_adapter import DiscordAdapter
from .matrix import expand_experiment_matrix
from .opencode_runtime import AgentRuntime
from .policy import ActionPolicy
from .schemas import (
    ActionRecord,
    AgentName,
    AgentTurnResult,
    ApprovalStatus,
    ArtifactRecord,
    ExperimentMatrix,
    JOB_TERMINAL_STATUSES,
    JobRecord,
    JobStatus,
    PolicyClassification,
    RequestedAction,
    RunCreateRequest,
    RunRecord,
    RunState,
    TERMINAL_STATES,
    TurnKind,
    TurnRecord,
    utc_now,
)
from .storage import ConcurrencyConflict, SqliteStore
from .workspaces import WorkspaceManager


class WorkflowError(RuntimeError):
    pass


class ResearchOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SqliteStore,
        runtime: AgentRuntime,
        workspaces: WorkspaceManager,
        contracts: EvaluationContractResolver,
        policy: ActionPolicy,
        cluster: ClusterExecutor,
        discord: DiscordAdapter,
    ) -> None:
        self.settings = settings
        self.store = store
        self.runtime = runtime
        self.workspaces = workspaces
        self.contracts = contracts
        self.policy = policy
        self.cluster = cluster
        self.discord = discord
        self._advance_lock = RLock()

    def _publish_latest(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        events = self.store.list_events(run_id)
        if not events:
            return
        try:
            status_message_id = self.discord.publish(
                thread_id=run.discord_thread_id,
                status_message_id=run.discord_status_message_id,
                event=events[-1],
            )
            if (
                status_message_id
                and status_message_id != run.discord_status_message_id
            ):
                current = self.store.get_run(run_id)
                self.store.replace_run(
                    current.model_copy(
                        update={
                            'discord_status_message_id': status_message_id,
                        }
                    ),
                    expected_version=current.version,
                )
        except Exception:
            # Discord is a replaceable projection and cannot fail the workflow.
            return

    def _event(
        self,
        run_id: str,
        *,
        source: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.store.append_event(
            run_id=run_id,
            source=source,
            event_type=event_type,
            payload=payload or {},
        )
        self._publish_latest(run_id)

    def _transition(
        self,
        run_id: str,
        target: RunState,
        *,
        payload: dict[str, Any] | None = None,
        updates: dict[str, Any] | None = None,
    ) -> RunRecord:
        run = self.store.transition_run(
            run_id,
            target,
            payload=payload,
            updates=updates,
        )
        self._publish_latest(run_id)
        return run

    def create_run(self, request: RunCreateRequest) -> RunRecord:
        with self._advance_lock:
            contract_id = (
                request.evaluation_contract_id
                or self.settings.default_evaluation_contract_id
            )
            contract_version = (
                request.evaluation_contract_version
                or self.settings.default_evaluation_contract_version
            )
            contract = self.contracts.resolve(contract_id, contract_version)
            run_id = uuid4().hex
            paths = self.workspaces.prepare(run_id)
            now = utc_now()
            record = RunRecord(
                run_id=run_id,
                objective=request.objective,
                state=RunState.CREATED,
                evaluation_contract_id=contract_id,
                evaluation_contract_version=contract_version,
                evaluation_contract_digest=contract.digest,
                beaker_workspace=str(paths.beaker),
                honeydew_workspace=str(paths.honeydew),
                shared_artifacts_path=str(paths.shared_artifacts),
                reports_path=str(paths.reports),
                maximum_turns=request.maximum_turns or self.settings.maximum_turns,
                maximum_runtime_seconds=(
                    request.maximum_runtime_seconds
                    or self.settings.maximum_runtime_seconds
                ),
                maximum_parallel_jobs=min(
                    request.maximum_parallel_jobs
                    or self.settings.maximum_parallel_jobs,
                    self.settings.maximum_parallel_jobs,
                ),
                created_at=now,
                updated_at=now,
            )
            self.store.create_run(
                record,
                one_active_run=self.settings.one_active_run,
            )
            try:
                thread_id = self.discord.create_thread(
                    run_id=run_id,
                    objective=request.objective,
                )
            except Exception:
                thread_id = None
            if thread_id:
                current = self.store.get_run(run_id)
                record = self.store.replace_run(
                    current.model_copy(
                        update={'discord_thread_id': thread_id}
                    ),
                    expected_version=current.version,
                )
            self._publish_latest(run_id)
            self._transition(run_id, RunState.PREPARING)
            self._transition(run_id, RunState.HONEYDEW_DRAFTING_PROTOCOL)
            try:
                self._draft_protocol(run_id)
            except Exception as exc:
                self._fail_run(run_id, exc)
                raise
            return self.store.get_run(run_id)

    def _check_turn_budget(self, run: RunRecord) -> None:
        if run.turn_number >= run.maximum_turns:
            self._transition(
                run.run_id,
                RunState.TIMED_OUT,
                payload={'reason': 'maximum turn count reached'},
            )
            raise WorkflowError('maximum turn count reached')
        if utc_now() > run.created_at + timedelta(seconds=run.maximum_runtime_seconds):
            self._transition(
                run.run_id,
                RunState.TIMED_OUT,
                payload={'reason': 'maximum runtime reached'},
            )
            raise WorkflowError('maximum runtime reached')

    def _run_agent_turn(
        self,
        *,
        run_id: str,
        agent: AgentName,
        prompt: str,
        expected_kind: TurnKind,
        input_event: dict[str, Any],
    ) -> tuple[TurnRecord, AgentTurnResult]:
        run = self.store.get_run(run_id)
        self._check_turn_budget(run)
        workspace = Path(
            run.honeydew_workspace
            if agent == AgentName.HONEYDEW
            else run.beaker_workspace
        )
        existing_session = (
            run.honeydew_session_id
            if agent == AgentName.HONEYDEW
            else run.beaker_session_id
        )
        session = self.runtime.ensure_session(
            run_id=run_id,
            agent=agent,
            workspace=workspace,
            existing_session_id=existing_session,
        )
        run = self.store.get_run(run_id)
        session_updates = {
            'current_agent': agent,
            'turn_number': run.turn_number + 1,
        }
        if agent == AgentName.HONEYDEW:
            session_updates.update(
                {
                    'honeydew_runtime_id': session.runtime_id,
                    'honeydew_session_id': session.session_id,
                }
            )
        else:
            session_updates.update(
                {
                    'beaker_runtime_id': session.runtime_id,
                    'beaker_session_id': session.session_id,
                }
            )
        self.store.replace_run(
            run.model_copy(update=session_updates),
            expected_version=run.version,
        )
        turn = TurnRecord(
            run_id=run_id,
            agent=agent,
            opencode_session_id=session.session_id,
            input_event=input_event,
            status='running',
        )
        self.store.save_turn(turn)
        self._event(
            run_id,
            source=agent.value,
            event_type='agent.turn_started',
            payload={
                'turn_id': turn.turn_id,
                'agent': agent.value,
                'kind': expected_kind.value,
            },
        )
        try:
            result, message_id = self.runtime.run_turn(
                run_id=run_id,
                agent=agent,
                workspace=workspace,
                session_id=session.session_id,
                prompt=prompt,
            )
            if result.kind != expected_kind:
                raise WorkflowError(
                    f'{agent.value} returned {result.kind}; expected {expected_kind}'
                )
            completed = turn.model_copy(
                update={
                    'opencode_message_id': message_id,
                    'structured_output': result,
                    'status': 'completed',
                    'updated_at': utc_now(),
                }
            )
            self.store.save_turn(completed)
            current = self.store.get_run(run_id)
            self.store.replace_run(
                current.model_copy(update={'current_agent': None}),
                expected_version=current.version,
            )
            self._event(
                run_id,
                source=agent.value,
                event_type='agent.turn_completed',
                payload={
                    'turn_id': completed.turn_id,
                    'kind': result.kind.value,
                    'summary': result.summary,
                    'recommended_next_state': (
                        result.recommended_next_state.value
                        if result.recommended_next_state
                        else None
                    ),
                    'message_to_other_agent': result.message_to_other_agent,
                },
            )
            return completed, result
        except Exception as exc:
            failed = turn.model_copy(
                update={
                    'status': 'failed',
                    'error': str(exc),
                    'updated_at': utc_now(),
                }
            )
            self.store.save_turn(failed)
            self._event(
                run_id,
                source=agent.value,
                event_type='agent.turn_completed',
                payload={
                    'turn_id': turn.turn_id,
                    'status': 'failed',
                    'error': str(exc),
                },
            )
            raise

    def _record_requested_actions(
        self,
        *,
        run_id: str,
        agent: AgentName,
        result: AgentTurnResult,
        turn_number: int,
    ) -> list[ActionRecord]:
        records: list[ActionRecord] = []
        for index, requested in enumerate(result.requested_actions):
            record = self.policy.build_record(
                run_id=run_id,
                proposed_by=agent,
                action=requested,
                ordinal=turn_number * 100 + index,
            )
            record = self.store.save_action(record)
            records.append(record)
            self._event(
                run_id,
                source=agent.value,
                event_type='action.proposed',
                payload={
                    'action_id': record.action_id,
                    'type': record.type,
                    'policy_classification': record.policy_classification.value,
                    'approval_status': record.approval_status.value,
                },
            )
        return records

    def _create_human_action(
        self,
        *,
        run_id: str,
        action_type: str,
        reason: str,
    ) -> ActionRecord:
        run = self.store.get_run(run_id)
        requested = RequestedAction(
            type=action_type,
            arguments={},
            reason=reason,
        )
        record = self.policy.build_record(
            run_id=run_id,
            proposed_by=AgentName.ORCHESTRATOR,
            action=requested,
            ordinal=run.turn_number * 1000 + len(self.store.list_actions(run_id)),
        )
        record = self.store.save_action(record)
        self._event(
            run_id,
            source='orchestrator',
            event_type='action.proposed',
            payload={
                'action_id': record.action_id,
                'type': record.type,
                'policy_classification': record.policy_classification.value,
                'approval_status': record.approval_status.value,
            },
        )
        return record

    def _draft_protocol(self, run_id: str, feedback: str | None = None) -> None:
        run = self.store.get_run(run_id)
        prompt = (
            'Draft a concrete program.md for this objective:\n\n'
            f'{run.objective}\n\n'
            f'Evaluation contract: contract://{run.evaluation_contract_id}/'
            f'{run.evaluation_contract_version}@{run.evaluation_contract_digest}\n'
            'Write program.md in your workspace. Include hypotheses, independent '
            'and dependent variables, controls, baselines, source references, '
            'required artifacts, evaluation criteria, budgets, stopping '
            'conditions, and explicit approval gates. Return it as a produced '
            'file with purpose "protocol".'
        )
        if feedback:
            prompt += f'\n\nHuman rejection feedback:\n{feedback}'
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            prompt=prompt,
            expected_kind=TurnKind.PROTOCOL_DRAFT,
            input_event={'objective': run.objective, 'feedback': feedback},
        )
        protocol_files = [
            item for item in result.produced_files if item.purpose == 'protocol'
        ]
        if len(protocol_files) != 1:
            raise WorkflowError('Honeydew must produce exactly one protocol file')
        destination, digest = self.workspaces.copy_agent_output(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            relative_path=protocol_files[0].path,
            destination_kind='protocol',
        )
        current = self.store.get_run(run_id)
        self.store.replace_run(
            current.model_copy(
                update={
                    'protocol_path': str(destination),
                    'protocol_version': current.protocol_version + 1,
                }
            ),
            expected_version=current.version,
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='artifact.recorded',
            payload={
                'type': 'protocol',
                'uri': f'artifact://{run_id}/protocol/program.md',
                'sha256': digest,
                'turn_id': turn.turn_id,
            },
        )
        self._create_human_action(
            run_id=run_id,
            action_type='approve_protocol',
            reason='Human approval is required before implementation.',
        )
        self._transition(run_id, RunState.AWAITING_PROTOCOL_APPROVAL)

    def approve_action(
        self,
        action_id: str,
        *,
        reviewer: str,
        reason: str,
    ) -> ActionRecord:
        with self._advance_lock:
            action = self.store.get_action(action_id)
            if action.approval_status == ApprovalStatus.APPROVED:
                self._resume_approved_action(action)
                return self.store.get_action(action_id)
            if action.approval_status != ApprovalStatus.PENDING:
                raise WorkflowError(
                    f'action is not pending: {action.approval_status.value}'
                )
            if (
                action.policy_classification
                == PolicyClassification.HONEYDEW_AND_HUMAN_APPROVAL
                and not action.honeydew_approved
            ):
                raise WorkflowError('Honeydew has not approved this action')
            approved = self.store.update_action(
                action_id,
                approval_status=ApprovalStatus.APPROVED,
                reviewer=reviewer,
                reason=reason,
            )
            self._event(
                action.run_id,
                source='orchestrator',
                event_type='action.approved',
                payload={'action_id': action_id, 'reviewer': reviewer},
            )
            self._resume_approved_action(approved)
            return approved

    def _resume_approved_action(self, action: ActionRecord) -> None:
        run = self.store.get_run(action.run_id)
        if action.type == 'approve_protocol':
            if run.state != RunState.AWAITING_PROTOCOL_APPROVAL:
                return
            self.workspaces.freeze_protocol(action.run_id)
            self._transition(action.run_id, RunState.BEAKER_IMPLEMENTING)
            self._beaker_implement(action.run_id)
        elif action.type == 'submit_experiment_matrix':
            if run.state != RunState.AWAITING_EXECUTION_APPROVAL:
                return
            self._submit_matrix(action)
        elif action.type == 'accept_final_report':
            if run.state != RunState.AWAITING_FINAL_ACCEPTANCE:
                return
            self._transition(action.run_id, RunState.COMPLETE)
            self._event(
                action.run_id,
                source='orchestrator',
                event_type='run.completed',
                payload={'accepted_by': action.reviewer},
            )

    def reject_action(
        self,
        action_id: str,
        *,
        reviewer: str,
        reason: str,
    ) -> ActionRecord:
        with self._advance_lock:
            action = self.store.update_action(
                action_id,
                approval_status=ApprovalStatus.REJECTED,
                reviewer=reviewer,
                reason=reason,
            )
            self._event(
                action.run_id,
                source='orchestrator',
                event_type='action.rejected',
                payload={
                    'action_id': action_id,
                    'reviewer': reviewer,
                    'reason': reason,
                },
            )
            run = self.store.get_run(action.run_id)
            if action.type == 'approve_protocol':
                self._transition(
                    action.run_id,
                    RunState.HONEYDEW_DRAFTING_PROTOCOL,
                )
                self._draft_protocol(action.run_id, feedback=reason)
            elif action.type == 'submit_experiment_matrix':
                self._transition(action.run_id, RunState.BEAKER_REVISING)
                self._beaker_revise(action.run_id, feedback=reason)
            elif action.type == 'accept_final_report':
                self._transition(
                    action.run_id,
                    RunState.HONEYDEW_WRITING_REPORT,
                )
                self._write_report(action.run_id, feedback=reason)
            elif run.state not in TERMINAL_STATES:
                self._fail_run(
                    action.run_id,
                    WorkflowError(f'unhandled rejected action: {action.type}'),
                )
            return action

    def _beaker_implement(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        prompt = (
            'Read the approved read-only program.md. Implement the bounded '
            'experiment in your isolated worktree, run lightweight tests, and '
            'propose one submit_experiment_matrix action. The action arguments '
            'must match the ExperimentMatrix schema and must not contain an '
            'evaluation entry point, Kubernetes manifest, contract file, or '
            'contract override. Do not execute cluster work.'
        )
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.BEAKER,
            prompt=prompt,
            expected_kind=TurnKind.IMPLEMENTATION_PROPOSAL,
            input_event={
                'protocol_path': run.protocol_path,
                'protocol_version': run.protocol_version,
            },
        )
        actions = self._record_requested_actions(
            run_id=run_id,
            agent=AgentName.BEAKER,
            result=result,
            turn_number=self.store.get_run(run_id).turn_number,
        )
        if not any(
            action.type == 'submit_experiment_matrix'
            and action.approval_status == ApprovalStatus.PENDING
            for action in actions
        ):
            raise WorkflowError(
                'Beaker did not produce a valid pending experiment matrix'
            )
        self._transition(run_id, RunState.HONEYDEW_REVIEWING)
        self._honeydew_review(run_id, implementation_turn_id=turn.turn_id)

    def _latest_pending_matrix_action(self, run_id: str) -> ActionRecord:
        matches = [
            action
            for action in self.store.list_actions(run_id)
            if action.type == 'submit_experiment_matrix'
            and action.approval_status == ApprovalStatus.PENDING
        ]
        if not matches:
            raise WorkflowError('run has no pending experiment matrix')
        return matches[-1]

    def _honeydew_review(
        self,
        run_id: str,
        *,
        implementation_turn_id: str,
    ) -> None:
        action = self._latest_pending_matrix_action(run_id)
        prompt = (
            'Review Beaker\'s implementation and proposed experiment matrix. '
            'Check controls, confounds, data leakage, comparability, resource '
            'bounds, required artifacts, and alignment with program.md and the '
            'immutable evaluation contract. Set done=true only when the matrix '
            'is methodologically acceptable. Do not submit the job.\n\n'
            f'Proposed matrix:\n{json.dumps(action.arguments, indent=2, sort_keys=True)}'
        )
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            prompt=prompt,
            expected_kind=TurnKind.METHODOLOGY_REVIEW,
            input_event={
                'implementation_turn_id': implementation_turn_id,
                'action_id': action.action_id,
            },
        )
        if not result.done:
            self.store.update_action(
                action.action_id,
                approval_status=ApprovalStatus.REJECTED,
                reviewer='honeydew',
                reason=result.summary,
            )
            self._event(
                run_id,
                source='honeydew',
                event_type='action.rejected',
                payload={
                    'action_id': action.action_id,
                    'reason': result.summary,
                },
            )
            self._transition(run_id, RunState.BEAKER_REVISING)
            self._beaker_revise(run_id, feedback=result.message_to_other_agent)
            return
        self.store.mark_action_honeydew_approved(
            action.action_id,
            review_turn_id=turn.turn_id,
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='action.approved',
            payload={
                'action_id': action.action_id,
                'approval_stage': 'methodology',
                'human_approval_still_required': True,
            },
        )
        self._transition(run_id, RunState.AWAITING_EXECUTION_APPROVAL)

    def _beaker_revise(self, run_id: str, *, feedback: str) -> None:
        prompt = (
            'Revise the implementation and experiment matrix in response to '
            'the review below. Run local checks and return a replacement '
            'submit_experiment_matrix action. Do not execute cluster work.\n\n'
            f'Review feedback:\n{feedback}'
        )
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.BEAKER,
            prompt=prompt,
            expected_kind=TurnKind.REVISION,
            input_event={'feedback': feedback},
        )
        actions = self._record_requested_actions(
            run_id=run_id,
            agent=AgentName.BEAKER,
            result=result,
            turn_number=self.store.get_run(run_id).turn_number,
        )
        if not any(
            item.type == 'submit_experiment_matrix'
            and item.approval_status == ApprovalStatus.PENDING
            for item in actions
        ):
            raise WorkflowError('Beaker revision lacks a valid experiment matrix')
        self._transition(run_id, RunState.HONEYDEW_REVIEWING)
        self._honeydew_review(run_id, implementation_turn_id=turn.turn_id)

    def _submit_matrix(self, action: ActionRecord) -> None:
        run = self.store.get_run(action.run_id)
        if run.state != RunState.AWAITING_EXECUTION_APPROVAL:
            raise WorkflowError(
                f'cannot submit matrix while run is {run.state.value}'
            )
        matrix = ExperimentMatrix.model_validate(action.arguments)
        contract = self.contracts.resolve(
            run.evaluation_contract_id,
            run.evaluation_contract_version,
        )
        if contract.digest != run.evaluation_contract_digest:
            raise WorkflowError('evaluation contract changed after run creation')
        specs = expand_experiment_matrix(
            run_id=run.run_id,
            action_id=action.action_id,
            matrix=matrix,
            contract=contract,
        )
        for spec in specs:
            record = JobRecord(
                job_id=spec.orchestrator_job_id,
                run_id=run.run_id,
                action_id=action.action_id,
                kubernetes_namespace=self.settings.kubernetes_namespace,
                status=JobStatus.QUEUED,
                requested_resources=spec.resources,
                evaluation_contract_id=spec.evaluation_contract_id,
                evaluation_contract_version=spec.evaluation_contract_version,
                evaluation_contract_digest=spec.evaluation_contract_digest,
                idempotency_key=spec.idempotency_key,
                variant_name=spec.variant_name,
                seed=spec.seed,
                spec=spec,
            )
            stored, created = self.store.create_job_if_absent(record)
            if created:
                self._event(
                    run.run_id,
                    source='orchestrator',
                    event_type='job.queued',
                    payload={
                        'job_id': stored.job_id,
                        'variant_name': stored.variant_name,
                        'seed': stored.seed,
                    },
                )
        self._transition(run.run_id, RunState.JOB_QUEUED)
        self._fill_job_capacity(run.run_id)

    def _fill_job_capacity(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        active = self.store.list_jobs(
            run_id,
            statuses={
                JobStatus.SUBMITTING,
                JobStatus.RUNNING,
                JobStatus.UNKNOWN,
            },
        )
        slots = max(0, run.maximum_parallel_jobs - len(active))
        queued = self.store.list_jobs(run_id, statuses={JobStatus.QUEUED})
        for job in queued[:slots]:
            submitting = self.store.update_job(
                job.model_copy(update={'status': JobStatus.SUBMITTING})
            )
            try:
                submission = self.cluster.submit(submitting.spec)
                status = (
                    submission.status
                    if submission.status in {JobStatus.QUEUED, JobStatus.RUNNING}
                    else JobStatus.RUNNING
                )
                updated = self.store.update_job(
                    submitting.model_copy(
                        update={
                            'status': status,
                            'external_run_id': submission.external_run_id,
                            'job_name': submission.job_name,
                            'kubernetes_uid': submission.kubernetes_uid,
                        }
                    )
                )
                self._event(
                    run_id,
                    source='cluster',
                    event_type='job.submitted',
                    payload={
                        'job_id': updated.job_id,
                        'external_run_id': updated.external_run_id,
                        'job_name': updated.job_name,
                        'contract_digest': updated.evaluation_contract_digest,
                    },
                )
            except Exception as exc:
                self.store.update_job(
                    submitting.model_copy(
                        update={
                            'status': JobStatus.FAILED,
                            'exit_information': {'submission_error': str(exc)},
                        }
                    )
                )
                self._event(
                    run_id,
                    source='cluster',
                    event_type='job.failed',
                    payload={
                        'job_id': submitting.job_id,
                        'phase': 'submission',
                        'error': str(exc),
                    },
                )
        run = self.store.get_run(run_id)
        active = self.store.list_jobs(
            run_id,
            statuses={
                JobStatus.QUEUED,
                JobStatus.SUBMITTING,
                JobStatus.RUNNING,
                JobStatus.UNKNOWN,
            },
        )
        if active and run.state == RunState.JOB_QUEUED:
            self._transition(run_id, RunState.JOB_RUNNING)
        elif not active and run.state in {
            RunState.JOB_QUEUED,
            RunState.JOB_RUNNING,
        }:
            self._transition(run_id, RunState.BEAKER_ANALYZING)
            self._analyze_results(run_id)

    def reconcile_run(self, run_id: str) -> RunRecord:
        with self._advance_lock:
            run = self.store.get_run(run_id)
            if run.state not in {RunState.JOB_QUEUED, RunState.JOB_RUNNING}:
                return run
            jobs = self.store.list_jobs(
                run_id,
                statuses={
                    JobStatus.QUEUED,
                    JobStatus.SUBMITTING,
                    JobStatus.RUNNING,
                    JobStatus.UNKNOWN,
                },
            )
            for job in jobs:
                if job.status == JobStatus.QUEUED:
                    continue
                if not job.external_run_id:
                    try:
                        submission = self.cluster.submit(job.spec)
                    except Exception as exc:
                        self.store.update_job(
                            job.model_copy(
                                update={
                                    'status': JobStatus.UNKNOWN,
                                    'exit_information': {
                                        'recovery_submission_error': str(exc)
                                    },
                                }
                            )
                        )
                        continue
                    job = self.store.update_job(
                        job.model_copy(
                            update={
                                'status': submission.status,
                                'external_run_id': submission.external_run_id,
                                'job_name': submission.job_name,
                                'kubernetes_uid': submission.kubernetes_uid,
                            }
                        )
                    )
                    self._event(
                        run_id,
                        source='cluster',
                        event_type='job.submitted',
                        payload={
                            'job_id': job.job_id,
                            'external_run_id': job.external_run_id,
                            'recovered': True,
                        },
                    )
                try:
                    snapshot = self.cluster.inspect(job.external_run_id)
                except Exception as exc:
                    self.store.update_job(
                        job.model_copy(
                            update={
                                'status': JobStatus.UNKNOWN,
                                'exit_information': {'inspection_error': str(exc)},
                            }
                        )
                    )
                    continue
                if snapshot.status == job.status:
                    continue
                updated = self.store.update_job(
                    job.model_copy(
                        update={
                            'status': snapshot.status,
                            'exit_information': snapshot.exit_information,
                        }
                    )
                )
                if snapshot.status in JOB_TERMINAL_STATUSES:
                    for artifact in snapshot.artifacts:
                        artifact_id = uuid5(
                            NAMESPACE_URL,
                            (
                                f'{job.job_id}:{artifact.uri}:'
                                f'{artifact.sha256}'
                            ),
                        ).hex
                        self.store.save_artifact(
                            ArtifactRecord(
                                artifact_id=artifact_id,
                                run_id=run_id,
                                job_id=job.job_id,
                                type=artifact.type,
                                uri=artifact.uri,
                                sha256=artifact.sha256,
                                metadata={
                                    **artifact.metadata,
                                    'evaluation_contract_id': (
                                        job.evaluation_contract_id
                                    ),
                                    'evaluation_contract_version': (
                                        job.evaluation_contract_version
                                    ),
                                    'evaluation_contract_digest': (
                                        job.evaluation_contract_digest
                                    ),
                                },
                            )
                        )
                        self._event(
                            run_id,
                            source='cluster',
                            event_type='artifact.recorded',
                            payload={
                                'job_id': job.job_id,
                                'uri': artifact.uri,
                                'sha256': artifact.sha256,
                            },
                        )
                    event_type = (
                        'job.completed'
                        if updated.status == JobStatus.SUCCEEDED
                        else 'job.failed'
                    )
                    self._event(
                        run_id,
                        source='cluster',
                        event_type=event_type,
                        payload={
                            'job_id': updated.job_id,
                            'status': updated.status.value,
                            'exit_information': updated.exit_information,
                        },
                    )
                elif snapshot.status == JobStatus.RUNNING:
                    self._event(
                        run_id,
                        source='cluster',
                        event_type='job.started',
                        payload={'job_id': updated.job_id},
                    )
            self._fill_job_capacity(run_id)
            return self.store.get_run(run_id)

    def _evidence_snapshot(self, run_id: str) -> dict[str, Any]:
        return {
            'jobs': [
                job.model_dump(mode='json')
                for job in self.store.list_jobs(run_id)
            ],
            'artifacts': [
                artifact.model_dump(mode='json')
                for artifact in self.store.list_artifacts(run_id)
            ],
        }

    def _analyze_results(self, run_id: str) -> None:
        evidence = self._evidence_snapshot(run_id)
        _, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.BEAKER,
            prompt=(
                'Analyze the authoritative job and artifact records below. A '
                'failed job is an observation to explain, not proof that the '
                'research run failed. Cite evidence URIs for every material '
                'claim.\n\n'
                + json.dumps(evidence, indent=2, sort_keys=True)
            ),
            expected_kind=TurnKind.EXPERIMENT_ANALYSIS,
            input_event=evidence,
        )
        self._record_requested_actions(
            run_id=run_id,
            agent=AgentName.BEAKER,
            result=result,
            turn_number=self.store.get_run(run_id).turn_number,
        )
        self._transition(run_id, RunState.HONEYDEW_VERIFYING)
        self._verify_results(run_id)

    def _verify_results(self, run_id: str) -> None:
        evidence = self._evidence_snapshot(run_id)
        _, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            prompt=(
                'Independently verify Beaker\'s important claims against these '
                'authoritative records and the approved program.md. Set '
                'done=true only if the evidence supports a final report. Cite '
                'artifact, job, event, Git, or contract URIs.\n\n'
                + json.dumps(evidence, indent=2, sort_keys=True)
            ),
            expected_kind=TurnKind.VERIFICATION,
            input_event=evidence,
        )
        if not result.done:
            self._transition(run_id, RunState.BEAKER_REVISING)
            self._beaker_revise(
                run_id,
                feedback=result.message_to_other_agent or result.summary,
            )
            return
        self._transition(run_id, RunState.HONEYDEW_WRITING_REPORT)
        self._write_report(run_id)

    def _write_report(self, run_id: str, feedback: str | None = None) -> None:
        evidence = self._evidence_snapshot(run_id)
        prompt = (
            'Write report.md for the human. Separate observations from '
            'inferences, cite authoritative evidence URIs, include failed runs '
            'and limitations, and do not overstate single-run results. Return '
            'the file with purpose "report".\n\n'
            + json.dumps(evidence, indent=2, sort_keys=True)
        )
        if feedback:
            prompt += f'\n\nHuman rejection feedback:\n{feedback}'
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            prompt=prompt,
            expected_kind=TurnKind.FINAL_REPORT,
            input_event={'evidence': evidence, 'feedback': feedback},
        )
        report_files = [
            item for item in result.produced_files if item.purpose == 'report'
        ]
        if len(report_files) != 1:
            raise WorkflowError('Honeydew must produce exactly one report file')
        destination, digest = self.workspaces.copy_agent_output(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            relative_path=report_files[0].path,
            destination_kind='report',
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='report.created',
            payload={
                'uri': f'artifact://{run_id}/reports/report.md',
                'path': str(destination),
                'sha256': digest,
                'turn_id': turn.turn_id,
            },
        )
        self._create_human_action(
            run_id=run_id,
            action_type='accept_final_report',
            reason='Human acceptance is required to complete the research run.',
        )
        self._transition(run_id, RunState.AWAITING_FINAL_ACCEPTANCE)

    def pause_run(self, run_id: str) -> RunRecord:
        # This deliberately does not take the advancement lock: pause must be
        # able to abort a model turn that currently owns that lock.
        run = self.store.get_run(run_id)
        if run.state in TERMINAL_STATES or run.state == RunState.PAUSED:
            return run
        self._abort_agent_turns(run)
        paused = self._transition(
            run_id,
            RunState.PAUSED,
            updates={'resume_state': run.state},
        )
        self._event(
            run_id,
            source='orchestrator',
            event_type='run.paused',
            payload={'resume_state': run.state.value},
        )
        return paused

    def resume_run(self, run_id: str) -> RunRecord:
        with self._advance_lock:
            run = self.store.get_run(run_id)
            if run.state != RunState.PAUSED or run.resume_state is None:
                raise WorkflowError('run is not resumable')
            target = run.resume_state
            resumed = self._transition(
                run_id,
                target,
                updates={'resume_state': None},
            )
            self._event(
                run_id,
                source='orchestrator',
                event_type='run.resumed',
                payload={'state': target.value},
            )
            self._recover_run(run_id)
            return self.store.get_run(run_id)

    def _abort_agent_turns(self, run: RunRecord) -> None:
        if run.honeydew_session_id:
            self.runtime.abort(
                run_id=run.run_id,
                agent=AgentName.HONEYDEW,
                session_id=run.honeydew_session_id,
            )
        if run.beaker_session_id:
            self.runtime.abort(
                run_id=run.run_id,
                agent=AgentName.BEAKER,
                session_id=run.beaker_session_id,
            )

    def cancel_run(self, run_id: str) -> RunRecord:
        # Like pause, cancellation must not wait for an active model turn.
        run = self.store.get_run(run_id)
        if run.state in TERMINAL_STATES:
            return run
        self._abort_agent_turns(run)
        cancellation_errors: list[str] = []
        for job in self.store.list_jobs(
            run_id,
            statuses={
                JobStatus.QUEUED,
                JobStatus.SUBMITTING,
                JobStatus.RUNNING,
                JobStatus.UNKNOWN,
            },
        ):
            if job.external_run_id:
                try:
                    self.cluster.cancel(job.external_run_id)
                except Exception as exc:
                    cancellation_errors.append(f'{job.job_id}: {exc}')
            self.store.update_job(
                job.model_copy(
                    update={
                        'status': JobStatus.CANCELLED,
                        'exit_information': {
                            **job.exit_information,
                            'cancel_requested': True,
                        },
                    }
                )
            )
        cancelled = self._transition(
            run_id,
            RunState.CANCELLED,
            payload={'cancellation_errors': cancellation_errors},
        )
        self._event(
            run_id,
            source='orchestrator',
            event_type='run.cancelled',
            payload={'cancellation_errors': cancellation_errors},
        )
        return cancelled

    def recover(self) -> list[str]:
        recovered: list[str] = []
        for run in self.store.list_active_runs():
            interrupted = self.store.mark_running_turns_interrupted(run.run_id)
            if interrupted:
                self._event(
                    run.run_id,
                    source='orchestrator',
                    event_type='run.recovered',
                    payload={'interrupted_turns': interrupted},
                )
            try:
                self._recover_run(run.run_id)
            except Exception as exc:
                self._fail_run(run.run_id, exc)
            recovered.append(run.run_id)
        return recovered

    def _recover_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        state = run.state
        if state == RunState.PREPARING:
            self._transition(run_id, RunState.HONEYDEW_DRAFTING_PROTOCOL)
            self._draft_protocol(run_id)
        elif state == RunState.HONEYDEW_DRAFTING_PROTOCOL:
            self._draft_protocol(run_id)
        elif state == RunState.BEAKER_IMPLEMENTING:
            pending = [
                action
                for action in self.store.list_actions(run_id)
                if action.type == 'submit_experiment_matrix'
                and action.approval_status == ApprovalStatus.PENDING
            ]
            if pending:
                self._transition(run_id, RunState.HONEYDEW_REVIEWING)
                self._honeydew_review(
                    run_id,
                    implementation_turn_id='recovered',
                )
            else:
                self._beaker_implement(run_id)
        elif state == RunState.HONEYDEW_REVIEWING:
            self._honeydew_review(
                run_id,
                implementation_turn_id='recovered',
            )
        elif state == RunState.BEAKER_REVISING:
            rejected = [
                action
                for action in self.store.list_actions(run_id)
                if action.type == 'submit_experiment_matrix'
                and action.approval_status == ApprovalStatus.REJECTED
            ]
            feedback = rejected[-1].reason if rejected else 'Resume the bounded revision.'
            self._beaker_revise(run_id, feedback=feedback)
        elif state == RunState.AWAITING_EXECUTION_APPROVAL:
            approved = [
                action
                for action in self.store.list_actions(run_id)
                if action.type == 'submit_experiment_matrix'
                and action.approval_status == ApprovalStatus.APPROVED
            ]
            if approved:
                self._submit_matrix(approved[-1])
        elif state in {RunState.JOB_QUEUED, RunState.JOB_RUNNING}:
            self.reconcile_run(run_id)
        elif state == RunState.BEAKER_ANALYZING:
            self._analyze_results(run_id)
        elif state == RunState.HONEYDEW_VERIFYING:
            self._verify_results(run_id)
        elif state == RunState.HONEYDEW_WRITING_REPORT:
            self._write_report(run_id)
        elif state == RunState.AWAITING_FINAL_ACCEPTANCE:
            approved = [
                action
                for action in self.store.list_actions(run_id)
                if action.type == 'accept_final_report'
                and action.approval_status == ApprovalStatus.APPROVED
            ]
            if approved:
                self._resume_approved_action(approved[-1])

    def _fail_run(self, run_id: str, exc: Exception) -> None:
        run = self.store.get_run(run_id)
        if run.state in TERMINAL_STATES or run.state == RunState.PAUSED:
            return
        try:
            self._transition(
                run_id,
                RunState.FAILED,
                payload={'error': str(exc)},
            )
        except (ConcurrencyConflict, ValueError):
            return
        self._event(
            run_id,
            source='orchestrator',
            event_type='run.failed',
            payload={'error': str(exc)},
        )
