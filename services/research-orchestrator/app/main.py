from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import json
import secrets
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from .cluster import FakeClusterExecutor, WorkflowApiClusterExecutor
from .config import Settings, get_settings
from .contracts import ContractIntegrityError, EvaluationContractResolver
from .discord_adapter import DisabledDiscordAdapter, DiscordHttpAdapter
from .discord_controls import DiscordControlGateway
from .engine import ResearchOrchestrator, WorkflowError
from .opencode_runtime import AgentRuntime, OpenCodeProcessRuntime
from .policy import ActionPolicy
from .schemas import (
    ActionRecord,
    ApprovalRequest,
    ArtifactListResponse,
    EventListResponse,
    RejectionRequest,
    RunCreateRequest,
    RunListResponse,
    RunRecord,
)
from .storage import ConcurrencyConflict, RecordNotFound, SqliteStore
from .watcher import JobWatcher
from .workspaces import WorkspaceError, WorkspaceManager


def build_engine(
    settings: Settings,
    *,
    runtime: AgentRuntime | None = None,
    cluster=None,
    discord=None,
) -> ResearchOrchestrator:
    store = SqliteStore(settings.database_path)
    runtime = runtime or OpenCodeProcessRuntime(settings)
    if cluster is None:
        cluster = (
            FakeClusterExecutor()
            if settings.cluster_execution_mode == 'fake'
            else WorkflowApiClusterExecutor(
                base_url=settings.cluster_execution_api_url,
                workload_id=settings.cluster_execution_workload_id,
                experiment_type=settings.cluster_execution_experiment_type,
            )
        )
    if discord is None:
        if (
            settings.discord_enabled
            and settings.discord_bot_token
            and settings.discord_channel_id
        ):
            discord = DiscordHttpAdapter(
                bot_token=settings.discord_bot_token,
                channel_id=settings.discord_channel_id,
                webhook_url=settings.discord_webhook_url,
            )
        else:
            discord = DisabledDiscordAdapter()
    return ResearchOrchestrator(
        settings=settings,
        store=store,
        runtime=runtime,
        workspaces=WorkspaceManager(
            workspace_root=settings.workspace_root,
            approved_repo_path=settings.approved_repo_path,
            approved_repo_ref=settings.approved_repo_ref,
        ),
        contracts=EvaluationContractResolver(
            settings.evaluation_contract_root
        ),
        policy=ActionPolicy(
            permitted_images=settings.permitted_job_images,
            maximum_cpu=settings.maximum_cpu,
            maximum_memory_gib=settings.maximum_memory_gib,
            maximum_gpus=settings.maximum_gpus,
            maximum_parallel_jobs=settings.maximum_parallel_jobs,
        ),
        cluster=cluster,
        discord=discord,
    )


def create_app(
    settings: Settings | None = None,
    *,
    engine: ResearchOrchestrator | None = None,
    start_watcher: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or build_engine(settings)
    watcher = JobWatcher(
        engine,
        poll_interval_seconds=settings.job_poll_interval_seconds,
    )
    discord_controls = None
    if (
        settings.discord_controls_enabled
        and settings.discord_bot_token
        and settings.discord_guild_id
    ):
        discord_controls = DiscordControlGateway(
            engine=engine,
            bot_token=settings.discord_bot_token,
            guild_id=settings.discord_guild_id,
            channel_id=settings.discord_channel_id or '',
            admin_role_id=settings.discord_admin_role_id,
            admin_user_ids=settings.discord_admin_user_ids,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        recovery_task = asyncio.create_task(
            asyncio.to_thread(engine.recover),
            name='research-orchestrator-recovery',
        )
        watcher_task = (
            asyncio.create_task(
                watcher.run(),
                name='research-orchestrator-job-watcher',
            )
            if start_watcher
            else None
        )
        discord_task = (
            asyncio.create_task(
                discord_controls.run(),
                name='research-orchestrator-discord-controls',
            )
            if discord_controls is not None
            else None
        )
        try:
            yield
        finally:
            watcher.stop()
            engine.runtime.close()
            if discord_controls is not None:
                await discord_controls.close()
            tasks = [recovery_task]
            if watcher_task is not None:
                tasks.append(watcher_task)
            if discord_task is not None:
                tasks.append(discord_task)
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title='Glasslab Research Orchestrator',
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.discord_controls = discord_controls

    def require_operator(
        supplied_token: str | None = Header(
            default=None,
            alias='X-Glasslab-Operator-Token',
        ),
    ) -> None:
        if not settings.require_operator_auth:
            return
        expected = settings.operator_api_token
        if not expected:
            raise HTTPException(
                status_code=503,
                detail='operator authentication is required but not configured',
            )
        if supplied_token is None or not secrets.compare_digest(
            supplied_token,
            expected,
        ):
            raise HTTPException(
                status_code=401,
                detail='valid operator token required',
            )

    def map_error(exc: Exception) -> HTTPException:
        if isinstance(exc, RecordNotFound):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(
            exc,
            (
                ConcurrencyConflict,
                ContractIntegrityError,
                WorkflowError,
                WorkspaceError,
            ),
        ):
            return HTTPException(status_code=409, detail=str(exc))
        return HTTPException(status_code=500, detail=str(exc))

    @app.get('/health')
    def health() -> dict[str, object]:
        return {
            'status': 'ok',
            'service': settings.app_name,
            'version': settings.app_version,
        }

    @app.get('/ready')
    def ready() -> dict[str, object]:
        try:
            database_ready = engine.store.ping()
            if (
                settings.require_operator_auth
                and not settings.operator_api_token
            ):
                raise RuntimeError(
                    'operator authentication is required but not configured'
                )
            contract = engine.contracts.resolve(
                settings.default_evaluation_contract_id,
                settings.default_evaluation_contract_version,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            'status': 'ready',
            'database': database_ready,
            'discord_controls': (
                'ready'
                if discord_controls is not None
                and discord_controls.client.is_ready()
                else 'disabled'
                if discord_controls is None
                else 'connecting'
            ),
            'evaluation_contract': {
                'contract_id': contract.descriptor.contract_id,
                'version': contract.descriptor.version,
                'digest': contract.digest,
            },
        }

    @app.post('/runs', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run(
        request: RunCreateRequest,
        _: None = Depends(require_operator),
    ) -> RunRecord:
        try:
            return engine.create_run(request)
        except Exception as exc:
            raise map_error(exc) from exc

    @app.get('/runs', response_model=RunListResponse)
    def list_runs() -> RunListResponse:
        return RunListResponse(runs=engine.store.list_runs())

    @app.get('/runs/{run_id}', response_model=RunRecord)
    def get_run(run_id: str) -> RunRecord:
        try:
            return engine.store.get_run(run_id)
        except Exception as exc:
            raise map_error(exc) from exc

    @app.get('/runs/{run_id}/events', response_model=EventListResponse)
    def get_events(
        run_id: str,
        after_sequence: int = Query(default=0, ge=0),
    ) -> EventListResponse:
        try:
            engine.store.get_run(run_id)
            return EventListResponse(
                events=engine.store.list_events(
                    run_id,
                    after_sequence=after_sequence,
                )
            )
        except Exception as exc:
            raise map_error(exc) from exc

    @app.get('/runs/{run_id}/artifacts', response_model=ArtifactListResponse)
    def get_artifacts(run_id: str) -> ArtifactListResponse:
        try:
            engine.store.get_run(run_id)
            return ArtifactListResponse(
                artifacts=engine.store.list_artifacts(run_id)
            )
        except Exception as exc:
            raise map_error(exc) from exc

    @app.post('/runs/{run_id}/pause', response_model=RunRecord)
    def pause_run(
        run_id: str,
        _: None = Depends(require_operator),
    ) -> RunRecord:
        try:
            return engine.pause_run(run_id)
        except Exception as exc:
            raise map_error(exc) from exc

    @app.post('/runs/{run_id}/resume', response_model=RunRecord)
    def resume_run(
        run_id: str,
        _: None = Depends(require_operator),
    ) -> RunRecord:
        try:
            return engine.resume_run(run_id)
        except Exception as exc:
            raise map_error(exc) from exc

    @app.post('/runs/{run_id}/cancel', response_model=RunRecord)
    def cancel_run(
        run_id: str,
        _: None = Depends(require_operator),
    ) -> RunRecord:
        try:
            return engine.cancel_run(run_id)
        except Exception as exc:
            raise map_error(exc) from exc

    @app.get('/actions/{action_id}', response_model=ActionRecord)
    def get_action(action_id: str) -> ActionRecord:
        try:
            return engine.store.get_action(action_id)
        except Exception as exc:
            raise map_error(exc) from exc

    @app.post('/actions/{action_id}/approve', response_model=ActionRecord)
    def approve_action(
        action_id: str,
        request: ApprovalRequest,
        _: None = Depends(require_operator),
    ) -> ActionRecord:
        try:
            return engine.approve_action(
                action_id,
                reviewer=request.reviewer,
                reason=request.reason,
            )
        except Exception as exc:
            raise map_error(exc) from exc

    @app.post('/actions/{action_id}/reject', response_model=ActionRecord)
    def reject_action(
        action_id: str,
        request: RejectionRequest,
        _: None = Depends(require_operator),
    ) -> ActionRecord:
        try:
            return engine.reject_action(
                action_id,
                reviewer=request.reviewer,
                reason=request.reason,
            )
        except Exception as exc:
            raise map_error(exc) from exc

    @app.get('/runs/{run_id}/events/stream')
    async def stream_events(
        run_id: str,
        after_sequence: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        try:
            engine.store.get_run(run_id)
        except Exception as exc:
            raise map_error(exc) from exc

        async def generate() -> AsyncIterator[str]:
            cursor = after_sequence
            while True:
                events = engine.store.list_events(
                    run_id,
                    after_sequence=cursor,
                )
                for event in events:
                    cursor = event.sequence_number
                    yield (
                        f'id: {event.sequence_number}\n'
                        f'event: {event.event_type}\n'
                        f'data: {json.dumps(event.model_dump(mode="json"))}\n\n'
                    )
                await asyncio.sleep(0.5)

        return StreamingResponse(
            generate(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            },
        )

    return app


app = create_app()
