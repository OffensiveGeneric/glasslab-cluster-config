from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from threading import RLock
from typing import Any
from uuid import uuid4, uuid5, NAMESPACE_URL

from .cluster import ClusterExecutor
from .config import Settings
from .contract_candidates import ContractCandidateManager
from .contracts import EvaluationContractResolver
from .discord_adapter import DiscordAdapter
from .datasets import DatasetIngestionManager
from .matrix import expand_experiment_matrix
from .opencode_runtime import AgentRuntime
from .policy import ActionPolicy
from .schemas import (
    ActionRecord,
    AgentName,
    AgentTurnResult,
    ApprovalStatus,
    ArtifactRecord,
    ContractCandidateRequest,
    EvaluationContractDescriptor,
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
from .task_bundles import (
    TaskBundleManager,
    TaskBundleRecord,
    TaskPreflight,
)
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
        contract_candidates: ContractCandidateManager,
        policy: ActionPolicy,
        cluster: ClusterExecutor,
        discord: DiscordAdapter,
        task_bundles: TaskBundleManager | None = None,
        datasets: DatasetIngestionManager | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.runtime = runtime
        self.workspaces = workspaces
        self.contracts = contracts
        self.contract_candidates = contract_candidates
        self.datasets = datasets or DatasetIngestionManager(
            store=store,
            root=settings.dataset_upload_root,
            shared_mount_root=settings.shared_mount_root,
            maximum_bytes=settings.maximum_dataset_upload_bytes,
        )
        self.task_bundles = task_bundles or TaskBundleManager(
            root=settings.task_bundle_root,
            shared_mount_root=settings.shared_mount_root,
            dataset_catalog_path=settings.benchmark_dataset_catalog_path,
            task_asset_root=settings.task_asset_root,
            maximum_asset_bytes=settings.maximum_task_asset_bytes,
            ingested_datasets=self.datasets,
        )
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
            task = (
                self.task_bundles.get(
                    request.task_id,
                    request.task_bundle_digest,
                )
                if request.task_id
                else None
            )
            contract_id = (
                request.evaluation_contract_id
                or (task.default_contract_id if task else None)
                or self.settings.default_evaluation_contract_id
            )
            contract_version = (
                request.evaluation_contract_version
                or (task.default_contract_version if task else None)
                or self.settings.default_evaluation_contract_version
            )
            contract = self.contracts.resolve(contract_id, contract_version)
            if task:
                preflight = self.task_preflight(task)
                if not preflight.ready:
                    raise WorkflowError(
                        'task preflight failed: '
                        + '; '.join(preflight.blocking_issues)
                    )
            run_id = uuid4().hex
            paths = self.workspaces.prepare(run_id)
            if task:
                self.workspaces.install_task_bundle(
                    run_id=run_id,
                    problem_path=task.problem_path,
                    evaluator_prompt_path=task.evaluator_prompt_path,
                )
            now = utc_now()
            record = RunRecord(
                run_id=run_id,
                objective=request.objective,
                state=RunState.CREATED,
                evaluation_contract_id=contract_id,
                evaluation_contract_version=contract_version,
                evaluation_contract_digest=contract.digest,
                task_id=task.task_id if task else None,
                task_bundle_digest=task.digest if task else None,
                task_bundle_path=task.archive_path if task else None,
                task_definition=(
                    task.model_dump(mode='json') if task else None
                ),
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

    def import_task_bundle(
        self,
        *,
        filename: str,
        content: bytes,
    ) -> TaskBundleRecord:
        with self._advance_lock:
            return self._compile_task_bundle(
                filename=filename,
                content=content,
            )

    def _compile_task_bundle(
        self,
        *,
        filename: str,
        content: bytes,
    ) -> TaskBundleRecord:
        digest = sha256(content).hexdigest()
        existing = self.task_bundles.find_by_digest(digest)
        if existing is not None:
            return existing
        staged = self.task_bundles.stage_archive(
            filename=filename,
            content=content,
        )
        compiler_id = f'task-compiler-{staged.digest[:16]}'
        workspace = staged.root / 'normalized'
        try:
            session = self.runtime.ensure_session(
                run_id=compiler_id,
                agent=AgentName.HONEYDEW,
                workspace=workspace,
                existing_session_id=None,
            )
            result, _ = self.runtime.run_turn(
                run_id=compiler_id,
                agent=AgentName.HONEYDEW,
                workspace=workspace,
                session_id=session.session_id,
                prompt=(
                    'Compile this task archive into a Glasslab TaskSpec. Read '
                    '`problem.md` and `eval_agent_prompt.md`. Select only one '
                    'approved runtime profile: cpu-ml-standard-v1 for tabular, '
                    'classical ML, and lightweight CPU work; or '
                    'gpu-ml-standard-v1 when the task materially requires '
                    'PyTorch/CUDA training. Identify every external dataset or '
                    'model asset as an asset proposal. Preserve any exact '
                    '`glasslab-dataset://<sha256>` reference from the problem '
                    'as approved_uri. Otherwise use a canonical public HTTPS '
                    'URL only when one is explicit or confidently known. Do '
                    'not invent credentials, private URLs, commands, images, '
                    'Kubernetes fields, or evaluator code. List exact metric '
                    'keys and evidence artifacts required by the rubric. Put '
                    'unresolved requirements in missing_inputs. Return kind '
                    '"task_spec", task_spec_proposal, no requested actions, '
                    'and done=true.'
                ),
            )
            if (
                result.kind != TurnKind.TASK_SPEC
                or result.task_spec_proposal is None
                or result.requested_actions
            ):
                raise WorkflowError(
                    'Honeydew task compiler did not return a valid TaskSpec'
                )
            return self.task_bundles.compile(
                staged,
                result.task_spec_proposal,
            )
        except Exception:
            self.task_bundles.discard_staged(staged)
            raise
        finally:
            self.runtime.release(
                run_id=compiler_id,
                agent=AgentName.HONEYDEW,
            )

    def task_preflight(self, task: TaskBundleRecord) -> TaskPreflight:
        try:
            self.contracts.resolve(
                task.default_contract_id,
                task.default_contract_version,
            )
            evaluator_ready = True
        except Exception:
            evaluator_ready = False
        return self.task_bundles.preflight(
            task,
            permitted_images=self.policy.permitted_images,
            evaluator_ready=evaluator_ready,
        )

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

    def _write_recovery_checkpoint(
        self,
        *,
        run_id: str,
        agent: AgentName,
        expected_kind: TurnKind,
        error: str,
    ) -> tuple[Path, dict[str, Any]]:
        run = self.store.get_run(run_id)
        workspace = Path(
            run.honeydew_workspace
            if agent == AgentName.HONEYDEW
            else run.beaker_workspace
        )
        completed = [
            turn
            for turn in self.store.list_turns(run_id)
            if turn.status == 'completed' and turn.structured_output is not None
        ][-4:]
        try:
            status = subprocess.run(
                ['git', 'status', '--short'],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            workspace_status = status.stdout.splitlines()[:80]
        except (OSError, subprocess.SubprocessError) as exc:
            workspace_status = [f'git status unavailable: {exc}']
        checkpoint = {
            'schema_version': 'glasslab-recovery-checkpoint-v1',
            'run_id': run_id,
            'agent': agent.value,
            'state': run.state.value,
            'expected_turn_kind': expected_kind.value,
            'objective': run.objective[:1000],
            'evaluation_contract': {
                'contract_id': run.evaluation_contract_id,
                'version': run.evaluation_contract_version,
                'digest': run.evaluation_contract_digest,
            },
            'protocol_path': run.protocol_path,
            'task_id': run.task_id,
            'failed_turn_error': error[:1000],
            'workspace_status': workspace_status,
            'recent_completed_turns': [
                {
                    'agent': turn.agent.value,
                    'kind': turn.structured_output.kind.value,
                    'summary': turn.structured_output.summary[:500],
                }
                for turn in completed
            ],
            'instruction': (
                'Continue the current bounded phase from the persisted worktree. '
                'Inspect existing files before editing and do not repeat completed '
                'work solely because the OpenCode session was rotated.'
            ),
        }
        path = self.workspaces.write_recovery_checkpoint(
            run_id=run_id,
            agent=agent,
            payload=checkpoint,
        )
        return path, checkpoint

    def _rotate_agent_session(
        self,
        *,
        run_id: str,
        agent: AgentName,
        expected_kind: TurnKind,
        error: str,
    ) -> None:
        release_error: str | None = None
        try:
            self.runtime.release(run_id=run_id, agent=agent)
        except Exception as exc:
            release_error = str(exc)
        current = self.store.get_run(run_id)
        updates: dict[str, Any] = {'current_agent': None}
        if agent == AgentName.HONEYDEW:
            updates.update(
                {
                    'honeydew_runtime_id': None,
                    'honeydew_session_id': None,
                }
            )
        else:
            updates.update(
                {
                    'beaker_runtime_id': None,
                    'beaker_session_id': None,
                }
            )
        self.store.replace_run(
            current.model_copy(update=updates),
            expected_version=current.version,
        )
        path, _ = self._write_recovery_checkpoint(
            run_id=run_id,
            agent=agent,
            expected_kind=expected_kind,
            error=error,
        )
        self._event(
            run_id,
            source='orchestrator',
            event_type='agent.session_rotated',
            payload={
                'agent': agent.value,
                'reason': error[:1000],
                'checkpoint_path': str(path),
                'next_session': 'fresh',
                'runtime_release_error': release_error,
            },
        )

    def _recovery_context(
        self,
        *,
        run_id: str,
        agent: AgentName,
    ) -> str:
        checkpoint_path = self.workspaces.paths(run_id).events / (
            f'{agent.value}-recovery-checkpoint.json'
        )
        if not checkpoint_path.is_file():
            return ''
        checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
        return (
            'This is a fresh OpenCode session after an interrupted or failed '
            'turn. The worktree and authoritative workflow state were preserved. '
            'Use this compact checkpoint and inspect the existing worktree before '
            'continuing:\n'
            + json.dumps(checkpoint, indent=2, sort_keys=True)
            + '\n\nCurrent bounded task:\n'
        )

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
        if existing_session is None:
            prompt = self._recovery_context(
                run_id=run_id,
                agent=agent,
            ) + prompt
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
                returned_kind = result.kind
                self._event(
                    run_id,
                    source='orchestrator',
                    event_type='agent.output_rejected',
                    payload={
                        'turn_id': turn.turn_id,
                        'returned_kind': returned_kind.value,
                        'expected_kind': expected_kind.value,
                        'repair_attempted': True,
                    },
                )
                result, message_id = self.runtime.run_turn(
                    run_id=run_id,
                    agent=agent,
                    workspace=workspace,
                    session_id=session.session_id,
                    prompt=(
                        'Structured kind correction. Your previous response '
                        f'used kind `{returned_kind.value}`, but this turn '
                        f'requires kind `{expected_kind.value}`. Complete the '
                        'original task and return a complete AgentTurnResult '
                        'with exactly that kind. Do not repeat an earlier '
                        'workflow phase.\n\nOriginal task:\n'
                        + prompt
                    ),
                )
                if result.kind != expected_kind:
                    raise WorkflowError(
                        f'{agent.value} returned {result.kind}; expected '
                        f'{expected_kind} after one focused repair'
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
            self._rotate_agent_session(
                run_id=run_id,
                agent=agent,
                expected_kind=expected_kind,
                error=str(exc),
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
                payload=self._approval_event_payload(record),
            )
        return records

    def _approval_event_payload(
        self,
        action: ActionRecord,
        *,
        human_approval_ready: bool | None = None,
    ) -> dict[str, Any]:
        run = self.store.get_run(action.run_id)
        if human_approval_ready is None:
            human_approval_ready = (
                action.approval_status == ApprovalStatus.PENDING
                and (
                    action.policy_classification
                    != PolicyClassification.HONEYDEW_AND_HUMAN_APPROVAL
                    or action.honeydew_approved
                )
            )
        artifacts = self.store.list_artifacts(action.run_id)
        relevant_artifact = next(
            (
                artifact
                for artifact in reversed(artifacts)
                if (
                    action.type == 'approve_protocol'
                    and artifact.type == 'protocol'
                )
                or (
                    action.type == 'accept_final_report'
                    and artifact.type == 'report'
                )
            ),
            None,
        )
        contract_proposal_artifact = next(
            (
                artifact
                for artifact in reversed(artifacts)
                if artifact.type == 'evaluation_contract_proposal'
            ),
            None,
        )
        effects = {
            'approve_protocol': (
                'Authorize Beaker to implement against this frozen protocol. '
                'This does not authorize a cluster job.'
            ),
            'submit_experiment_matrix': (
                'Authorize the orchestrator to validate, expand, and submit '
                'this experiment matrix under the recorded resource limits.'
            ),
            'accept_final_report': (
                'Accept the report as the final output and mark this research '
                'run complete. This does not publish it externally.'
            ),
            'propose_evaluation_contract': (
                'Promote the sealed, Honeydew-reviewed evaluation contract '
                'into the trusted catalog and bind this run to its exact digest. '
                'This does not authorize a cluster job.'
            ),
        }
        payload: dict[str, Any] = {
            'action_id': action.action_id,
            'type': action.type,
            'policy_classification': action.policy_classification.value,
            'approval_status': action.approval_status.value,
            'human_approval_ready': human_approval_ready,
            'honeydew_approved': action.honeydew_approved,
            'objective': run.objective,
            'reason': action.reason,
            'effect': effects.get(
                action.type,
                'Authorize the stored action under its deterministic policy.',
            ),
            'arguments': action.arguments,
            'evaluation_contract': {
                'contract_id': run.evaluation_contract_id,
                'version': run.evaluation_contract_version,
                'digest': run.evaluation_contract_digest,
            },
        }
        if relevant_artifact is not None:
            payload['artifact'] = {
                'type': relevant_artifact.type,
                'uri': relevant_artifact.uri,
                'sha256': relevant_artifact.sha256,
            }
        if contract_proposal_artifact is not None:
            payload['contract_proposal'] = (
                contract_proposal_artifact.metadata.get('proposal')
            )
            payload['contract_binding'] = (
                contract_proposal_artifact.metadata.get('technical_binding')
            )
        if action.type == 'propose_evaluation_contract':
            candidate = next(
                (
                    artifact
                    for artifact in reversed(artifacts)
                    if artifact.type == 'evaluation_contract_candidate'
                    and artifact.metadata.get('action_id') == action.action_id
                ),
                None,
            )
            if candidate is not None:
                payload['artifact'] = {
                    'type': candidate.type,
                    'uri': candidate.uri,
                    'sha256': candidate.sha256,
                }
                payload['contract_candidate'] = candidate.metadata
        if action.type == 'approve_protocol':
            payload['protocol_version'] = run.protocol_version
        return payload

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
            payload=self._approval_event_payload(record),
        )
        return record

    def _save_local_artifact(
        self,
        *,
        run_id: str,
        artifact_type: str,
        uri: str,
        digest: str,
        metadata: dict[str, Any],
    ) -> ArtifactRecord:
        artifact = ArtifactRecord(
            artifact_id=uuid5(
                NAMESPACE_URL,
                f'{run_id}:{uri}:{digest}',
            ).hex,
            run_id=run_id,
            type=artifact_type,
            uri=uri,
            sha256=digest,
            metadata=metadata,
        )
        return self.store.save_artifact(artifact)

    def _latest_contract_proposal(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:
        matches = [
            artifact
            for artifact in self.store.list_artifacts(run_id)
            if artifact.type == 'evaluation_contract_proposal'
        ]
        if not matches:
            return None
        proposal = matches[-1].metadata.get('proposal')
        return proposal if isinstance(proposal, dict) else None

    def _contract_binding_compatible(self, run_id: str) -> bool:
        run = self.store.get_run(run_id)
        proposal = self._latest_contract_proposal(run_id)
        if proposal is None:
            return False
        try:
            contract = self.contracts.resolve(
                run.evaluation_contract_id,
                run.evaluation_contract_version,
            )
        except ValueError:
            return False
        descriptor = contract.descriptor
        primary = proposal.get('primary_metric')
        resources = proposal.get('resource_constraints')
        required_artifacts = proposal.get('required_artifacts')
        if not isinstance(primary, dict) or not isinstance(resources, dict):
            return False
        if not isinstance(required_artifacts, list):
            return False
        ceiling = descriptor.resource_constraints
        allowed_artifacts = set(descriptor.required_artifacts)
        if (
            descriptor.contract_id == 'generic-task-integrity-v1'
            and run.task_definition
        ):
            allowed_artifacts.update(
                str(item)
                for item in run.task_definition.get('required_artifacts', [])
            )
        return bool(
            contract.digest == run.evaluation_contract_digest
            and proposal.get('evaluator_type') == descriptor.contract_id
            and primary.get('name') == descriptor.manifest.get('primary_metric')
            and primary.get('direction')
            == descriptor.manifest.get('primary_metric_direction')
            and set(str(item) for item in required_artifacts).issubset(
                allowed_artifacts
            )
            and float(resources.get('cpu', float('inf'))) <= ceiling.cpu
            and float(resources.get('memory_gib', float('inf')))
            <= ceiling.memory_gib
            and int(resources.get('gpus', self.policy.maximum_gpus + 1))
            <= ceiling.gpus
            and int(
                resources.get(
                    'wallclock_minutes',
                    ceiling.wallclock_minutes + 1,
                )
            )
            <= ceiling.wallclock_minutes
        )

    def _draft_protocol(self, run_id: str, feedback: str | None = None) -> None:
        run = self.store.get_run(run_id)
        task_context = ''
        if run.task_definition:
            bound = self.contracts.resolve(
                run.evaluation_contract_id,
                run.evaluation_contract_version,
            )
            generic_task = (
                run.task_definition.get('compilation_source')
                == 'honeydew-task-spec'
            )
            task_context = (
                '\n\nThis is an imported research task. Read the immutable '
                '`benchmark-task/problem.md` and '
                '`benchmark-task/eval_agent_prompt.md` files. Treat the task '
                'requirements and evaluator rubric as binding source material. '
                + (
                    'The generic integrity evaluator is a baseline. Use it '
                    'only if artifact and metric-key checks are scientifically '
                    'sufficient; otherwise propose the task-specific evaluator '
                    'that Beaker should implement and Honeydew should review. '
                    if generic_task
                    else
                    'Do not redesign the evaluator contract or request a new '
                    'harness; the repository-controlled contract is already '
                    'bound to this legacy task. Make '
                    'evaluation_contract_proposal exactly match this installed '
                    'descriptor. '
                )
                + '\nInstalled descriptor:\n'
                + json.dumps(
                    bound.descriptor.model_dump(mode='json'),
                    indent=2,
                    sort_keys=True,
                )
            )
        prompt = (
            'Draft a concrete program.md for this objective:\n\n'
            f'{run.objective}\n\n'
            f'Evaluation contract: contract://{run.evaluation_contract_id}/'
            f'{run.evaluation_contract_version}@{run.evaluation_contract_digest}\n'
            'Write program.md in your workspace. Include hypotheses, independent '
            'and dependent variables, controls, baselines, source references, '
            'required artifacts, evaluation criteria, budgets, stopping '
            'conditions, and explicit approval gates. Return it as a produced '
            'file with purpose "protocol". Also populate '
            'evaluation_contract_proposal with the scientific evaluator type, '
            'primary metric and direction, minimum meaningful effect, '
            'guardrails, required artifacts, budget policy, resource ceilings, '
            'and rationale. Propose data and metrics only. Do not propose '
            'executable paths, container images, commands, or checksums; those '
            'remain controlled by the orchestrator.'
            + task_context
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
        proposal = result.evaluation_contract_proposal
        if proposal is None:
            raise WorkflowError(
                'Honeydew must return an evaluation contract proposal'
            )
        proposal_resources = proposal.resource_constraints
        if (
            proposal_resources.cpu > self.policy.maximum_cpu
            or proposal_resources.memory_gib > self.policy.maximum_memory_gib
            or proposal_resources.gpus > self.policy.maximum_gpus
        ):
            raise WorkflowError(
                'Honeydew contract proposal exceeds orchestrator resource ceilings'
            )
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
        uri = f'artifact://{run_id}/protocol/program.md'
        self._save_local_artifact(
            run_id=run_id,
            artifact_type='protocol',
            uri=uri,
            digest=digest,
            metadata={
                'path': str(destination),
                'protocol_version': current.protocol_version + 1,
                'turn_id': turn.turn_id,
            },
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='artifact.recorded',
            payload={
                'type': 'protocol',
                'uri': uri,
                'path': str(destination),
                'sha256': digest,
                'turn_id': turn.turn_id,
            },
        )
        resolved_contract = self.contracts.resolve(
            run.evaluation_contract_id,
            run.evaluation_contract_version,
        )
        descriptor = resolved_contract.descriptor
        technical_primary_metric = str(
            descriptor.manifest.get('primary_metric', '')
        )
        ceiling = descriptor.resource_constraints
        allowed_artifacts = set(descriptor.required_artifacts)
        if (
            descriptor.contract_id == 'generic-task-integrity-v1'
            and run.task_definition
        ):
            allowed_artifacts.update(
                str(item)
                for item in run.task_definition.get('required_artifacts', [])
            )
        binding_compatible = (
            proposal.evaluator_type == descriptor.contract_id
            and proposal.primary_metric.name == technical_primary_metric
            and proposal.primary_metric.direction
            == descriptor.manifest.get('primary_metric_direction')
            and set(proposal.required_artifacts).issubset(
                allowed_artifacts
            )
            and proposal_resources.cpu <= ceiling.cpu
            and proposal_resources.memory_gib <= ceiling.memory_gib
            and proposal_resources.gpus <= ceiling.gpus
            and proposal_resources.wallclock_minutes
            <= ceiling.wallclock_minutes
        )
        proposal_payload = proposal.model_dump(mode='json')
        proposal_path = (
            Path(run.shared_artifacts_path)
            / 'evaluation-contract-proposal.json'
        )
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_bytes = (
            json.dumps(proposal_payload, indent=2, sort_keys=True) + '\n'
        ).encode()
        proposal_path.write_bytes(proposal_bytes)
        proposal_digest = sha256(proposal_bytes).hexdigest()
        proposal_uri = (
            f'artifact://{run_id}/shared-artifacts/'
            'evaluation-contract-proposal.json'
        )
        technical_binding = {
            'status': (
                'compatible'
                if binding_compatible
                else 'requires_new_harness'
            ),
            'contract_id': run.evaluation_contract_id,
            'version': run.evaluation_contract_version,
            'digest': run.evaluation_contract_digest,
        }
        self._save_local_artifact(
            run_id=run_id,
            artifact_type='evaluation_contract_proposal',
            uri=proposal_uri,
            digest=proposal_digest,
            metadata={
                'path': str(proposal_path),
                'turn_id': turn.turn_id,
                'proposal': proposal_payload,
                'technical_binding': technical_binding,
            },
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='artifact.recorded',
            payload={
                'type': 'evaluation_contract_proposal',
                'uri': proposal_uri,
                'path': str(proposal_path),
                'sha256': proposal_digest,
                'turn_id': turn.turn_id,
                'proposal': proposal_payload,
                'technical_binding': technical_binding,
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
            try:
                self._resume_approved_action(approved)
            except Exception as exc:
                self._handle_approved_action_failure(approved, exc)
                raise
            return approved

    def _handle_approved_action_failure(
        self,
        action: ActionRecord,
        exc: Exception,
    ) -> None:
        jobs = [
            job
            for job in self.store.list_jobs(action.run_id)
            if job.action_id == action.action_id
        ]
        deterministic_matrix_failure = (
            action.type == 'submit_experiment_matrix'
            and isinstance(exc, ValueError)
            and not jobs
        )
        resulting_state = (
            RunState.BEAKER_REVISING
            if deterministic_matrix_failure
            else RunState.PAUSED
        )
        if deterministic_matrix_failure:
            self.store.mark_action_execution_failed(
                action.action_id,
                reason=f'Approved action could not execute: {exc}',
            )
        current = self.store.get_run(action.run_id)
        self._event(
            action.run_id,
            source='orchestrator',
            event_type='action.execution_failed',
            payload={
                'action_id': action.action_id,
                'type': action.type,
                'objective': current.objective,
                'error': str(exc),
                'jobs_created': len(jobs),
                'artifacts_created': len(
                    [
                        artifact
                        for artifact in self.store.list_artifacts(action.run_id)
                        if artifact.job_id in {job.job_id for job in jobs}
                    ]
                ),
                'retryable': not deterministic_matrix_failure,
                'resulting_state': resulting_state.value,
                'next_step': (
                    'Beaker will revise the matrix before another approval.'
                    if deterministic_matrix_failure
                    else (
                        'The run is paused. Reconcile any recorded jobs, then '
                        'resume to retry the authoritative action.'
                    )
                ),
            },
        )
        if current.state in TERMINAL_STATES or current.state == RunState.PAUSED:
            return
        if deterministic_matrix_failure:
            self._transition(action.run_id, RunState.BEAKER_REVISING)
            self._beaker_revise(
                action.run_id,
                feedback=(
                    'The approved matrix failed deterministic execution '
                    f'validation: {exc}'
                ),
            )
            return
        self.pause_run(action.run_id)

    def _resume_approved_action(self, action: ActionRecord) -> None:
        run = self.store.get_run(action.run_id)
        if action.type == 'approve_protocol':
            if run.state != RunState.AWAITING_PROTOCOL_APPROVAL:
                return
            self.workspaces.freeze_protocol(action.run_id)
            if self._contract_binding_compatible(action.run_id):
                self._transition(action.run_id, RunState.BEAKER_PLANNING)
                self._beaker_plan(action.run_id)
            else:
                self._transition(
                    action.run_id,
                    RunState.BEAKER_DRAFTING_CONTRACT,
                )
                self._beaker_draft_contract(action.run_id)
        elif action.type == 'propose_evaluation_contract':
            if run.state != RunState.AWAITING_CONTRACT_PROMOTION:
                return
            self._promote_contract_candidate(action)
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
            existing = self.store.get_action(action_id)
            if existing.approval_status == ApprovalStatus.REJECTED:
                self._event(
                    existing.run_id,
                    source='orchestrator',
                    event_type='action.rejection_resumed',
                    payload={
                        'action_id': action_id,
                        'reviewer': reviewer,
                        'reason': reason,
                    },
                )
                self._resume_rejected_action(existing, feedback=reason)
                return self.store.get_action(action_id)
            if existing.approval_status != ApprovalStatus.PENDING:
                raise WorkflowError(
                    f'action is not pending: {existing.approval_status.value}'
                )
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
            self._resume_rejected_action(action, feedback=reason)
            return action

    def _resume_rejected_action(
        self,
        action: ActionRecord,
        *,
        feedback: str,
    ) -> None:
        run = self.store.get_run(action.run_id)
        if action.type == 'approve_protocol':
            if run.state != RunState.AWAITING_PROTOCOL_APPROVAL:
                return
            self._transition(
                action.run_id,
                RunState.HONEYDEW_DRAFTING_PROTOCOL,
            )
            self._draft_protocol(action.run_id, feedback=feedback)
        elif action.type == 'submit_experiment_matrix':
            if run.state != RunState.AWAITING_EXECUTION_APPROVAL:
                return
            self._transition(action.run_id, RunState.BEAKER_REVISING)
            self._beaker_revise(action.run_id, feedback=feedback)
        elif action.type == 'accept_final_report':
            if run.state != RunState.AWAITING_FINAL_ACCEPTANCE:
                return
            self._transition(
                action.run_id,
                RunState.HONEYDEW_WRITING_REPORT,
            )
            self._write_report(action.run_id, feedback=feedback)
        elif action.type == 'propose_evaluation_contract':
            if run.state != RunState.AWAITING_CONTRACT_PROMOTION:
                return
            self._transition(
                action.run_id,
                RunState.BEAKER_DRAFTING_CONTRACT,
            )
            self._beaker_draft_contract(action.run_id, feedback=feedback)
        elif run.state not in TERMINAL_STATES:
            self._fail_run(
                action.run_id,
                WorkflowError(f'unhandled rejected action: {action.type}'),
            )

    def _beaker_draft_contract(
        self,
        run_id: str,
        *,
        feedback: str | None = None,
    ) -> None:
        proposal = self._latest_contract_proposal(run_id)
        if proposal is None:
            raise WorkflowError('run has no evaluation contract proposal')
        prompt = (
            'Draft an immutable evaluation-contract candidate for the approved '
            'program.md. Create a self-contained directory under '
            '`contract-candidate/<contract-id>/<version>/` containing '
            'contract.json, the execution wrapper, evaluator, input and output '
            'JSON schemas, and concise test vectors or tests. The descriptor '
            'must contain only the EvaluationContractDescriptor fields, set '
            'container_image_digest to null, and put both primary_metric and '
            'primary_metric_direction in manifest. execution_wrapper and '
            'evaluation_entry_point must each be a relative path to a real '
            'Python file inside the candidate directory, not a command or '
            'module reference. Do not write '
            'contract.sha256; the orchestrator owns sealing. Run lightweight '
            'local checks. Return exactly one `propose_evaluation_contract` '
            'action with contract_id, semantic version, candidate_path, and '
            'rationale. Do not request publication, Kubernetes, registry, or '
            'shared-storage access.\n\nApproved scientific proposal:\n'
            + json.dumps(proposal, indent=2, sort_keys=True)
        )
        if feedback:
            prompt += f'\n\nReview feedback:\n{feedback}'
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.BEAKER,
            prompt=prompt,
            expected_kind=TurnKind.CONTRACT_CANDIDATE,
            input_event={'proposal': proposal, 'feedback': feedback},
        )
        actions = self._record_requested_actions(
            run_id=run_id,
            agent=AgentName.BEAKER,
            result=result,
            turn_number=self.store.get_run(run_id).turn_number,
        )
        candidates = [
            action
            for action in actions
            if action.type == 'propose_evaluation_contract'
            and action.approval_status == ApprovalStatus.PENDING
        ]
        if len(candidates) != 1:
            denied = [
                action.reason
                for action in actions
                if action.type == 'propose_evaluation_contract'
            ]
            raise WorkflowError(
                'Beaker must propose exactly one valid contract candidate'
                + (f': {"; ".join(denied)}' if denied else '')
            )
        action = candidates[0]
        request = ContractCandidateRequest.model_validate(action.arguments)
        workspace = Path(self.store.get_run(run_id).beaker_workspace).resolve()
        source = (workspace / request.candidate_path).resolve()
        if not source.is_relative_to(workspace):
            raise WorkflowError('contract candidate escapes Beaker workspace')
        try:
            sealed = self.contract_candidates.seal(
                source=source,
                contract_id=request.contract_id,
                version=request.version,
            )
            descriptor = sealed.descriptor
            primary = proposal.get('primary_metric')
            resources = proposal.get('resource_constraints')
            required_artifacts = proposal.get('required_artifacts')
            if (
                request.contract_id != proposal.get('evaluator_type')
                or not isinstance(primary, dict)
                or descriptor.manifest.get('primary_metric')
                != primary.get('name')
                or descriptor.manifest.get('primary_metric_direction')
                != primary.get('direction')
                or not isinstance(required_artifacts, list)
                or not set(required_artifacts).issubset(
                    descriptor.required_artifacts
                )
                or not isinstance(resources, dict)
                or float(resources.get('cpu', float('inf')))
                > descriptor.resource_constraints.cpu
                or float(resources.get('memory_gib', float('inf')))
                > descriptor.resource_constraints.memory_gib
                or int(resources.get('gpus', self.policy.maximum_gpus + 1))
                > descriptor.resource_constraints.gpus
            ):
                raise WorkflowError(
                    'candidate descriptor does not implement the approved '
                    'scientific contract proposal'
                )
        except (OSError, ValueError, WorkflowError) as exc:
            feedback_message = (
                'The orchestrator rejected the candidate during deterministic '
                f'validation: {exc}'
            )
            self.store.update_action(
                action.action_id,
                approval_status=ApprovalStatus.REJECTED,
                reviewer='orchestrator',
                reason=feedback_message,
            )
            self._event(
                run_id,
                source='orchestrator',
                event_type='contract.candidate_rejected',
                payload={
                    'action_id': action.action_id,
                    'reason': feedback_message,
                    'retrying': True,
                },
            )
            self._beaker_draft_contract(
                run_id,
                feedback=feedback_message,
            )
            return
        review_path = self.workspaces.copy_contract_candidate_for_review(
            run_id=run_id,
            source=sealed.sealed_path,
            contract_id=sealed.contract_id,
            version=sealed.version,
            digest=sealed.digest,
        )
        uri = (
            f'artifact://{run_id}/contract-candidates/'
            f'{sealed.contract_id}/{sealed.version}@{sealed.digest}'
        )
        artifact = self._save_local_artifact(
            run_id=run_id,
            artifact_type='evaluation_contract_candidate',
            uri=uri,
            digest=sealed.digest,
            metadata={
                'action_id': action.action_id,
                'turn_id': turn.turn_id,
                'contract_id': sealed.contract_id,
                'version': sealed.version,
                'sealed_path': str(sealed.sealed_path),
                'review_path': str(review_path),
                'descriptor': descriptor.model_dump(mode='json'),
            },
        )
        self._event(
            run_id,
            source='orchestrator',
            event_type='contract.candidate_sealed',
            payload={
                'action_id': action.action_id,
                'artifact_id': artifact.artifact_id,
                'uri': uri,
                'contract_id': sealed.contract_id,
                'version': sealed.version,
                'digest': sealed.digest,
                'review_path': str(review_path),
            },
        )
        self._transition(run_id, RunState.HONEYDEW_REVIEWING_CONTRACT)
        self._honeydew_review_contract(
            run_id,
            action=action,
            artifact=artifact,
        )

    def _honeydew_review_contract(
        self,
        run_id: str,
        *,
        action: ActionRecord,
        artifact: ArtifactRecord,
    ) -> None:
        prompt = (
            'Review the sealed evaluation-contract candidate against the '
            'approved program.md and scientific proposal. Inspect every file '
            'under the read-only review path. Check metric semantics, schemas, '
            'required artifacts, leakage risks, deterministic behavior, '
            'resource limits, and whether the wrapper preserves the immutable '
            'evaluation boundary. Set done=true only if it is suitable for '
            'admin promotion. Set requested_actions to an empty list; the '
            'orchestrator already owns the promotion action. Do not propose '
            'file, approval, or transition actions. Do not edit the candidate.\n\n'
            f'Review path: {artifact.metadata["review_path"]}\n'
            f'Descriptor:\n'
            + json.dumps(
                artifact.metadata['descriptor'],
                indent=2,
                sort_keys=True,
            )
        )
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.HONEYDEW,
            prompt=prompt,
            expected_kind=TurnKind.METHODOLOGY_REVIEW,
            input_event={
                'action_id': action.action_id,
                'artifact_id': artifact.artifact_id,
            },
        )
        if not result.done:
            reason = result.summary
            self.store.update_action(
                action.action_id,
                approval_status=ApprovalStatus.REJECTED,
                reviewer='honeydew',
                reason=reason,
            )
            self._event(
                run_id,
                source='honeydew',
                event_type='action.rejected',
                payload={
                    'action_id': action.action_id,
                    'reason': reason,
                },
            )
            self._transition(run_id, RunState.BEAKER_DRAFTING_CONTRACT)
            self._beaker_draft_contract(
                run_id,
                feedback=result.message_to_other_agent or reason,
            )
            return
        approved = self.store.mark_action_honeydew_approved(
            action.action_id,
            review_turn_id=turn.turn_id,
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='contract.candidate_reviewed',
            payload={
                'action_id': action.action_id,
                'artifact_id': artifact.artifact_id,
                'digest': artifact.sha256,
                'human_approval_still_required': True,
            },
        )
        self._transition(run_id, RunState.AWAITING_CONTRACT_PROMOTION)
        self._event(
            run_id,
            source='orchestrator',
            event_type='action.human_approval_requested',
            payload=self._approval_event_payload(
                approved,
                human_approval_ready=True,
            ),
        )

    def _promote_contract_candidate(self, action: ActionRecord) -> None:
        matches = [
            artifact
            for artifact in self.store.list_artifacts(action.run_id)
            if artifact.type == 'evaluation_contract_candidate'
            and artifact.metadata.get('action_id') == action.action_id
        ]
        if len(matches) != 1:
            raise WorkflowError(
                'approved contract action has no unique sealed candidate'
            )
        artifact = matches[0]
        destination = self.contract_candidates.promote(
            sealed_path=Path(str(artifact.metadata['sealed_path'])),
            expected_digest=artifact.sha256,
        )
        descriptor = EvaluationContractDescriptor.model_validate(
            artifact.metadata['descriptor']
        )
        current = self.store.get_run(action.run_id)
        self.store.replace_run(
            current.model_copy(
                update={
                    'evaluation_contract_id': descriptor.contract_id,
                    'evaluation_contract_version': descriptor.version,
                    'evaluation_contract_digest': artifact.sha256,
                }
            ),
            expected_version=current.version,
        )
        resolved = self.contracts.resolve(
            descriptor.contract_id,
            descriptor.version,
        )
        if resolved.digest != artifact.sha256:
            raise WorkflowError('promoted contract cannot be resolved by digest')
        self._event(
            action.run_id,
            source='orchestrator',
            event_type='contract.promoted',
            payload={
                'action_id': action.action_id,
                'contract_id': descriptor.contract_id,
                'version': descriptor.version,
                'digest': artifact.sha256,
                'path': str(destination),
                'reviewer': action.reviewer,
            },
        )
        if not self._contract_binding_compatible(action.run_id):
            raise WorkflowError(
                'promoted contract remains incompatible with the protocol'
            )
        self._transition(action.run_id, RunState.BEAKER_PLANNING)
        self._beaker_plan(action.run_id)

    def _beaker_plan(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        task_context = ''
        if run.task_definition:
            task_context = (
                ' This is an imported task; inspect `benchmark-task/problem.md` '
                'and `benchmark-task/eval_agent_prompt.md` as binding inputs.'
            )
        _, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.BEAKER,
            prompt=(
                'Read the approved read-only program.md and inspect the existing '
                'worktree. Write implementation-plan.md containing a concise, '
                'task-specific sequence of independently checkable implementation '
                'steps, the files likely to change, lightweight local checks, and '
                'the intended experiment-matrix shape. Preserve freedom to revise '
                'the plan when repository evidence requires it. Do not implement '
                'the experiment in this turn, request actions, or execute cluster '
                'work. Return exactly that file with purpose "implementation" and '
                'kind "implementation_plan".'
                + task_context
            ),
            expected_kind=TurnKind.IMPLEMENTATION_PLAN,
            input_event={
                'protocol_path': run.protocol_path,
                'protocol_version': run.protocol_version,
            },
        )
        plans = [
            item
            for item in result.produced_files
            if item.path == 'implementation-plan.md'
            and item.purpose == 'implementation'
        ]
        if len(plans) != 1 or result.requested_actions:
            raise WorkflowError(
                'Beaker planning must produce implementation-plan.md and no actions'
            )
        plan_path = Path(run.beaker_workspace) / 'implementation-plan.md'
        if not plan_path.is_file():
            raise WorkflowError('Beaker did not create implementation-plan.md')
        digest = sha256(plan_path.read_bytes()).hexdigest()
        self._event(
            run_id,
            source='beaker',
            event_type='agent.plan_created',
            payload={
                'path': 'implementation-plan.md',
                'sha256': digest,
            },
        )
        self._transition(run_id, RunState.BEAKER_IMPLEMENTING)
        self._beaker_implement(run_id)

    def _beaker_implement(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        plan_path = Path(run.beaker_workspace) / 'implementation-plan.md'
        if not plan_path.is_file():
            self._transition(run_id, RunState.BEAKER_PLANNING)
            self._beaker_plan(run_id)
            return
        task_context = ''
        if run.task_definition:
            source = run.task_definition['source_subdirectory']
            task_context = (
                '\nThis is an imported benchmark task. Read '
                '`benchmark-task/problem.md`, `benchmark-task/eval_agent_prompt.md`, '
                'and the frozen `program.md`. Put the complete executable '
                f'solution under `{source}/`, including `run.py`. The run must '
                'use only dataset paths supplied through '
                '`GLASSLAB_DATASET_BINDINGS_JSON`, write all outputs beneath '
                '`GLASSLAB_OUTPUT_DIR`, and make no network calls. Use the '
                'exact preselected runner image and resource request:\n'
                + json.dumps(
                    {
                        'runner_image': run.task_definition['runner_image'],
                        'resources': run.task_definition['resources'],
                        'required_artifacts': (
                            run.task_definition['required_artifacts']
                        ),
                        'datasets': run.task_definition['datasets'],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        prompt = (
            'Read the approved read-only program.md and implementation-plan.md. '
            'Execute the task-specific plan in your isolated worktree, adapting '
            'it when repository evidence requires. Finish the bounded experiment '
            'runner, run the listed lightweight checks, and '
            'propose one submit_experiment_matrix action. The action arguments '
            'must match the ExperimentMatrix schema and must not contain an '
            'evaluation entry point, Kubernetes manifest, contract file, or '
            'contract override. Do not execute cluster work.'
            f'\n\nPermitted runner images: '
            f'{json.dumps(sorted(self.policy.permitted_images))}'
            '\nResource ceilings: '
            f'cpu={self.policy.maximum_cpu}, '
            f'memory_gib={self.policy.maximum_memory_gib}, '
            f'gpus={self.policy.maximum_gpus}, '
            'maximum_parallel_jobs='
            f'{self.policy.maximum_parallel_jobs}.'
            + task_context
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
        self._advance_after_matrix_proposal(
            run_id=run_id,
            implementation_turn_id=turn.turn_id,
            actions=actions,
        )

    def _beaker_finalize(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if not self._has_imported_task_implementation(run):
            self._transition(run_id, RunState.BEAKER_IMPLEMENTING)
            self._beaker_implement(run_id)
            return
        task = run.task_definition
        assert task is not None
        prompt = (
            'Finalize the existing imported benchmark implementation after an '
            'interrupted implementation turn. Inspect implementation-plan.md and '
            f'`{task["source_subdirectory"]}/run.py` as the preserved checkpoint. '
            'Do not redesign or broadly rewrite the solution and do not run the '
            'full benchmark. Run only narrow local validation such as Python '
            'compilation and the smallest available smoke check. Fix concrete '
            'blocking defects you observe, create the base configuration if it is '
            'missing, and return exactly one submit_experiment_matrix action. The '
            'action must match the ExperimentMatrix schema and must not contain an '
            'evaluation entry point, Kubernetes manifest, contract file, or '
            'contract override. Do not execute cluster work.\n\n'
            'Use exactly this imported-task execution boundary:\n'
            + json.dumps(
                {
                    'runner_image': task['runner_image'],
                    'resources': task['resources'],
                    'required_artifacts': task['required_artifacts'],
                    'datasets': task['datasets'],
                },
                indent=2,
                sort_keys=True,
            )
            + '\n\nPermitted runner images: '
            + json.dumps(sorted(self.policy.permitted_images))
            + '\nResource ceilings: '
            f'cpu={self.policy.maximum_cpu}, '
            f'memory_gib={self.policy.maximum_memory_gib}, '
            f'gpus={self.policy.maximum_gpus}, '
            'maximum_parallel_jobs='
            f'{self.policy.maximum_parallel_jobs}.'
        )
        turn, result = self._run_agent_turn(
            run_id=run_id,
            agent=AgentName.BEAKER,
            prompt=prompt,
            expected_kind=TurnKind.IMPLEMENTATION_PROPOSAL,
            input_event={
                'protocol_path': run.protocol_path,
                'protocol_version': run.protocol_version,
                'checkpoint': (
                    f'{task["source_subdirectory"]}/run.py'
                ),
                'recovery_mode': 'finalize_existing_implementation',
            },
        )
        actions = self._record_requested_actions(
            run_id=run_id,
            agent=AgentName.BEAKER,
            result=result,
            turn_number=self.store.get_run(run_id).turn_number,
        )
        self._advance_after_matrix_proposal(
            run_id=run_id,
            implementation_turn_id=turn.turn_id,
            actions=actions,
        )

    def _advance_after_matrix_proposal(
        self,
        *,
        run_id: str,
        implementation_turn_id: str,
        actions: list[ActionRecord],
    ) -> None:
        pending = any(
            action.type == 'submit_experiment_matrix'
            and action.approval_status == ApprovalStatus.PENDING
            for action in actions
        )
        if not pending:
            feedback = self._matrix_revision_feedback(actions)
            self._transition(run_id, RunState.BEAKER_REVISING)
            self._beaker_revise(
                run_id,
                feedback=feedback,
            )
            return
        self._transition(run_id, RunState.HONEYDEW_REVIEWING)
        self._honeydew_review(
            run_id,
            implementation_turn_id=implementation_turn_id,
        )

    @staticmethod
    def _has_imported_task_implementation(run: RunRecord) -> bool:
        if not run.task_definition:
            return False
        workspace = Path(run.beaker_workspace).resolve()
        source = (
            workspace / str(run.task_definition['source_subdirectory'])
        ).resolve()
        entrypoint = source / 'run.py'
        return (
            source.is_relative_to(workspace)
            and entrypoint.is_file()
            and not entrypoint.is_symlink()
        )

    @staticmethod
    def _matrix_revision_feedback(actions: list[ActionRecord]) -> str:
        denied = [
            action.reason
            for action in actions
            if action.type == 'submit_experiment_matrix'
            and action.approval_status == ApprovalStatus.DENIED
        ]
        if denied:
            return (
                'The orchestrator policy denied the proposed experiment '
                f'matrix: {"; ".join(denied)}'
            )
        return (
            'No valid submit_experiment_matrix action was returned. Propose '
            'exactly one matrix that satisfies the supplied policy bounds.'
        )

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
        preflight_error = self._matrix_preflight_error(
            run_id=run_id,
            action=action,
        )
        if not result.done or preflight_error:
            rejection_reason = (
                f'Deterministic matrix preflight failed: {preflight_error}'
                if preflight_error
                else result.summary
            )
            self.store.update_action(
                action.action_id,
                approval_status=ApprovalStatus.REJECTED,
                reviewer='honeydew',
                reason=rejection_reason,
            )
            self._event(
                run_id,
                source='honeydew',
                event_type='action.rejected',
                payload={
                    'action_id': action.action_id,
                    'reason': rejection_reason,
                },
            )
            self._transition(run_id, RunState.BEAKER_REVISING)
            feedback = result.message_to_other_agent.strip()
            if preflight_error:
                feedback = (
                    f'{feedback}\n\n' if feedback else ''
                ) + rejection_reason
            self._beaker_revise(run_id, feedback=feedback or rejection_reason)
            return
        approved_action = self.store.mark_action_honeydew_approved(
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
        self._event(
            run_id,
            source='orchestrator',
            event_type='action.human_approval_requested',
            payload=self._approval_event_payload(
                approved_action,
                human_approval_ready=True,
            ),
        )

    def _matrix_preflight_error(
        self,
        *,
        run_id: str,
        action: ActionRecord,
    ) -> str | None:
        try:
            matrix = ExperimentMatrix.model_validate(action.arguments)
            run = self.store.get_run(run_id)
            if not self._contract_binding_compatible(run_id):
                return (
                    'installed evaluation contract is incompatible with the '
                    'approved protocol; promote a matching contract first'
                )
            workspace = Path(run.beaker_workspace).resolve()
            base_config = (workspace / matrix.base_config).resolve()
            if (
                not base_config.is_relative_to(workspace)
                or not base_config.is_file()
            ):
                return (
                    'base_config does not exist inside the Beaker workspace: '
                    f'{matrix.base_config}'
                )
            if run.task_definition:
                expected_image = str(run.task_definition['runner_image'])
                expected_resources = run.task_definition['resources']
                if matrix.runner_image != expected_image:
                    return (
                        'imported benchmark requires runner_image '
                        f'{expected_image}'
                    )
                if matrix.resources.model_dump(mode='json') != expected_resources:
                    return (
                        'imported benchmark resources must exactly match the '
                        'preselected task resource profile'
                    )
            contract = self.contracts.resolve(
                run.evaluation_contract_id,
                run.evaluation_contract_version,
            )
            if contract.digest != run.evaluation_contract_digest:
                return 'evaluation contract changed after run creation'
            expand_experiment_matrix(
                run_id=run_id,
                action_id=action.action_id,
                matrix=matrix,
                contract=contract,
            )
        except ValueError as exc:
            return str(exc)
        return None

    def _beaker_revise(self, run_id: str, *, feedback: str) -> None:
        run = self.store.get_run(run_id)
        task_context = ''
        if run.task_definition:
            task_context = (
                '\nPreserve the imported benchmark boundary: all executable '
                f'files stay under `{run.task_definition["source_subdirectory"]}`, '
                'datasets come only from the provided bindings, and the '
                'preselected image/resources must not change.'
            )
        prompt = (
            'Revise the implementation and experiment matrix in response to '
            'the review below. Run local checks and return a replacement '
            'submit_experiment_matrix action. Do not execute cluster work.\n\n'
            f'Permitted runner images: '
            f'{json.dumps(sorted(self.policy.permitted_images))}\n'
            'Resource ceilings: '
            f'cpu={self.policy.maximum_cpu}, '
            f'memory_gib={self.policy.maximum_memory_gib}, '
            f'gpus={self.policy.maximum_gpus}, '
            'maximum_parallel_jobs='
            f'{self.policy.maximum_parallel_jobs}.\n\n'
            f'Review feedback:\n{feedback}'
            + task_context
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
        pending = any(
            item.type == 'submit_experiment_matrix'
            and item.approval_status == ApprovalStatus.PENDING
            for item in actions
        )
        if not pending:
            self._beaker_revise(
                run_id,
                feedback=self._matrix_revision_feedback(actions),
            )
            return
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
        execution: dict[str, object] | None = None
        if run.task_definition:
            task = run.task_definition
            source_path, source_digest = self.workspaces.package_source_bundle(
                run_id=run.run_id,
                source_subdirectory=str(task['source_subdirectory']),
            )
            shared_root = Path(self.settings.shared_mount_root).resolve()
            source_relative = source_path.resolve().relative_to(shared_root)
            execution = {
                'workload_id': task['workload_id'],
                'experiment_type': task['experiment_type'],
                'task_bundle': {
                    'uri': task['archive_uri'],
                    'sha256': task['digest'],
                },
                'source_bundle': {
                    'uri': 's3://artifacts/' + source_relative.as_posix(),
                    'sha256': source_digest,
                },
                'workspace_command': task['command'],
                'dataset_contracts': [
                    {
                        'name': dataset['name'],
                        'role': dataset['role'],
                        'contains_labels': dataset['contains_labels'],
                        'asset': {
                            'uri': dataset['uri'],
                            'sha256': dataset['sha256'],
                        },
                    }
                    for dataset in task['datasets']
                ],
                'dataset_bindings': {
                    dataset['name']: dataset['uri']
                    for dataset in task['datasets']
                },
                'task_spec': task.get('task_spec'),
            }
            self._save_local_artifact(
                run_id=run.run_id,
                artifact_type='source_bundle',
                uri='artifact://' + source_relative.as_posix(),
                digest=source_digest,
                metadata={'path': str(source_path)},
            )
        specs = expand_experiment_matrix(
            run_id=run.run_id,
            action_id=action.action_id,
            matrix=matrix,
            contract=contract,
            execution=execution,
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
        uri = f'artifact://{run_id}/reports/report.md'
        self._save_local_artifact(
            run_id=run_id,
            artifact_type='report',
            uri=uri,
            digest=digest,
            metadata={
                'path': str(destination),
                'turn_id': turn.turn_id,
            },
        )
        self._event(
            run_id,
            source='honeydew',
            event_type='report.created',
            payload={
                'uri': uri,
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

    def pause_run(
        self,
        run_id: str,
        *,
        requested_by: str | None = None,
        reason: str | None = None,
    ) -> RunRecord:
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
            payload={
                'resume_state': run.state.value,
                'requested_by': requested_by,
                'reason': reason,
            },
        )
        return paused

    def resume_run(
        self,
        run_id: str,
        *,
        requested_by: str | None = None,
        reason: str | None = None,
    ) -> RunRecord:
        with self._advance_lock:
            run = self.store.get_run(run_id)
            if run.state != RunState.PAUSED or run.resume_state is None:
                raise WorkflowError('run is not resumable')
            self._rotate_failed_session_before_resume(run)
            run = self.store.get_run(run_id)
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
                payload={
                    'state': target.value,
                    'requested_by': requested_by,
                    'reason': reason,
                },
            )
            try:
                self._recover_run(run_id)
            except Exception as exc:
                self.pause_run(
                    run_id,
                    requested_by='orchestrator',
                    reason=f'Resumed workflow failed: {exc}',
                )
                raise
            return self.store.get_run(run_id)

    def _rotate_failed_session_before_resume(self, run: RunRecord) -> None:
        phase: dict[RunState, tuple[AgentName, TurnKind]] = {
            RunState.HONEYDEW_DRAFTING_PROTOCOL: (
                AgentName.HONEYDEW,
                TurnKind.PROTOCOL_DRAFT,
            ),
            RunState.BEAKER_DRAFTING_CONTRACT: (
                AgentName.BEAKER,
                TurnKind.CONTRACT_CANDIDATE,
            ),
            RunState.HONEYDEW_REVIEWING_CONTRACT: (
                AgentName.HONEYDEW,
                TurnKind.METHODOLOGY_REVIEW,
            ),
            RunState.BEAKER_PLANNING: (
                AgentName.BEAKER,
                TurnKind.IMPLEMENTATION_PLAN,
            ),
            RunState.BEAKER_IMPLEMENTING: (
                AgentName.BEAKER,
                TurnKind.IMPLEMENTATION_PROPOSAL,
            ),
            RunState.BEAKER_FINALIZING: (
                AgentName.BEAKER,
                TurnKind.IMPLEMENTATION_PROPOSAL,
            ),
            RunState.HONEYDEW_REVIEWING: (
                AgentName.HONEYDEW,
                TurnKind.METHODOLOGY_REVIEW,
            ),
            RunState.BEAKER_REVISING: (
                AgentName.BEAKER,
                TurnKind.REVISION,
            ),
            RunState.BEAKER_ANALYZING: (
                AgentName.BEAKER,
                TurnKind.EXPERIMENT_ANALYSIS,
            ),
            RunState.HONEYDEW_VERIFYING: (
                AgentName.HONEYDEW,
                TurnKind.VERIFICATION,
            ),
            RunState.HONEYDEW_WRITING_REPORT: (
                AgentName.HONEYDEW,
                TurnKind.FINAL_REPORT,
            ),
        }
        selected = phase.get(run.resume_state)
        if selected is None:
            return
        agent, expected_kind = selected
        session_id = (
            run.honeydew_session_id
            if agent == AgentName.HONEYDEW
            else run.beaker_session_id
        )
        if session_id is None:
            return
        failed_turns = [
            turn
            for turn in self.store.list_turns(run.run_id)
            if turn.agent == agent and turn.status == 'failed'
        ]
        if not failed_turns or failed_turns[-1].opencode_session_id != session_id:
            return
        self._rotate_agent_session(
            run_id=run.run_id,
            agent=agent,
            expected_kind=expected_kind,
            error=(
                'resume detected a failed turn still attached to the active '
                'OpenCode session'
            ),
        )

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

    def cancel_run(
        self,
        run_id: str,
        *,
        requested_by: str | None = None,
        reason: str | None = None,
    ) -> RunRecord:
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
            payload={
                'cancellation_errors': cancellation_errors,
                'requested_by': requested_by,
                'reason': reason,
            },
        )
        self._event(
            run_id,
            source='orchestrator',
            event_type='run.cancelled',
            payload={
                'cancellation_errors': cancellation_errors,
                'requested_by': requested_by,
                'reason': reason,
            },
        )
        return cancelled

    def recover(self) -> list[str]:
        for run in self.store.list_runs():
            self._backfill_local_artifacts(run.run_id)
        recovered: list[str] = []
        for run in self.store.list_active_runs():
            running_turns = [
                turn
                for turn in self.store.list_turns(run.run_id)
                if turn.status == 'running'
            ]
            interrupted = self.store.mark_running_turns_interrupted(run.run_id)
            if interrupted:
                self._event(
                    run.run_id,
                    source='orchestrator',
                    event_type='run.recovered',
                    payload={'interrupted_turns': interrupted},
                )
                started_events = {
                    str(event.payload.get('turn_id')): event
                    for event in self.store.list_events(run.run_id)
                    if event.event_type == 'agent.turn_started'
                }
                for turn in running_turns:
                    event = started_events.get(turn.turn_id)
                    raw_kind = (
                        event.payload.get('kind')
                        if event is not None
                        else TurnKind.IMPLEMENTATION_PROPOSAL.value
                    )
                    try:
                        expected_kind = TurnKind(str(raw_kind))
                    except ValueError:
                        expected_kind = TurnKind.IMPLEMENTATION_PROPOSAL
                    self._rotate_agent_session(
                        run_id=run.run_id,
                        agent=turn.agent,
                        expected_kind=expected_kind,
                        error=(
                            'orchestrator restarted during active agent turn'
                        ),
                    )
            try:
                self._recover_run(run.run_id)
            except Exception as exc:
                current = self.store.get_run(run.run_id)
                resumable_agent_states = {
                    RunState.HONEYDEW_DRAFTING_PROTOCOL,
                    RunState.BEAKER_DRAFTING_CONTRACT,
                    RunState.HONEYDEW_REVIEWING_CONTRACT,
                    RunState.BEAKER_PLANNING,
                    RunState.BEAKER_IMPLEMENTING,
                    RunState.BEAKER_FINALIZING,
                    RunState.HONEYDEW_REVIEWING,
                    RunState.BEAKER_REVISING,
                    RunState.BEAKER_ANALYZING,
                    RunState.HONEYDEW_VERIFYING,
                    RunState.HONEYDEW_WRITING_REPORT,
                }
                if current.state in resumable_agent_states:
                    self._event(
                        run.run_id,
                        source='orchestrator',
                        event_type='run.recovery_failed',
                        payload={
                            'state': current.state.value,
                            'error': str(exc),
                            'next_step': (
                                'The run is paused at the same phase. Resume '
                                'to retry the bounded agent turn.'
                            ),
                        },
                    )
                    self.pause_run(run.run_id)
                else:
                    self._fail_run(run.run_id, exc)
            recovered.append(run.run_id)
        return recovered

    def _backfill_local_artifacts(self, run_id: str) -> None:
        for event in self.store.list_events(run_id):
            payload = event.payload
            artifact_type = None
            if (
                event.event_type == 'artifact.recorded'
                and payload.get('type') == 'protocol'
            ):
                artifact_type = 'protocol'
            elif (
                event.event_type == 'artifact.recorded'
                and payload.get('type') == 'evaluation_contract_proposal'
            ):
                artifact_type = 'evaluation_contract_proposal'
            elif event.event_type == 'report.created':
                artifact_type = 'report'
            if artifact_type is None:
                continue
            uri = payload.get('uri')
            digest = payload.get('sha256')
            if not isinstance(uri, str) or not isinstance(digest, str):
                continue
            self._save_local_artifact(
                run_id=run_id,
                artifact_type=artifact_type,
                uri=uri,
                digest=digest,
                metadata={
                    key: value
                    for key, value in payload.items()
                    if key not in {'type', 'uri', 'sha256'}
                },
            )

    def _recover_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        state = run.state
        contract_sensitive_states = {
            RunState.BEAKER_PLANNING,
            RunState.BEAKER_IMPLEMENTING,
            RunState.BEAKER_FINALIZING,
            RunState.HONEYDEW_REVIEWING,
            RunState.BEAKER_REVISING,
            RunState.AWAITING_EXECUTION_APPROVAL,
        }
        if state in contract_sensitive_states and not self._contract_binding_compatible(
            run_id
        ):
            for action in self.store.list_actions(run_id):
                if (
                    action.type == 'submit_experiment_matrix'
                    and action.approval_status == ApprovalStatus.PENDING
                ):
                    self.store.update_action(
                        action.action_id,
                        approval_status=ApprovalStatus.REJECTED,
                        reviewer='orchestrator',
                        reason=(
                            'The approved protocol requires a different '
                            'evaluation contract.'
                        ),
                    )
            self._transition(run_id, RunState.BEAKER_DRAFTING_CONTRACT)
            self._beaker_draft_contract(
                run_id,
                feedback=(
                    'Recovery detected that the installed evaluation contract '
                    'does not implement the approved protocol. Draft the '
                    'required immutable contract candidate before continuing.'
                ),
            )
            return
        if state == RunState.PREPARING:
            self._transition(run_id, RunState.HONEYDEW_DRAFTING_PROTOCOL)
            self._draft_protocol(run_id)
        elif state == RunState.HONEYDEW_DRAFTING_PROTOCOL:
            self._draft_protocol(run_id)
        elif state == RunState.BEAKER_DRAFTING_CONTRACT:
            self._beaker_draft_contract(run_id)
        elif state == RunState.HONEYDEW_REVIEWING_CONTRACT:
            candidates = [
                artifact
                for artifact in self.store.list_artifacts(run_id)
                if artifact.type == 'evaluation_contract_candidate'
            ]
            if not candidates:
                self._transition(run_id, RunState.BEAKER_DRAFTING_CONTRACT)
                self._beaker_draft_contract(
                    run_id,
                    feedback='The sealed contract candidate was not recoverable.',
                )
                return
            artifact = candidates[-1]
            action = self.store.get_action(str(artifact.metadata['action_id']))
            self._honeydew_review_contract(
                run_id,
                action=action,
                artifact=artifact,
            )
        elif state == RunState.AWAITING_CONTRACT_PROMOTION:
            approved = [
                action
                for action in self.store.list_actions(run_id)
                if action.type == 'propose_evaluation_contract'
                and action.approval_status == ApprovalStatus.APPROVED
            ]
            if approved:
                self._promote_contract_candidate(approved[-1])
        elif state == RunState.BEAKER_PLANNING:
            self._beaker_plan(run_id)
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
            elif self._has_imported_task_implementation(run):
                self._transition(run_id, RunState.BEAKER_FINALIZING)
                self._beaker_finalize(run_id)
            else:
                self._beaker_implement(run_id)
        elif state == RunState.BEAKER_FINALIZING:
            self._beaker_finalize(run_id)
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
