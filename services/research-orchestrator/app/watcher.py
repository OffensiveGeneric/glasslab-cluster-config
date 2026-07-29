from __future__ import annotations

import asyncio

from .engine import ResearchOrchestrator
from .schemas import RunState


class JobWatcher:
    def __init__(
        self,
        engine: ResearchOrchestrator,
        *,
        poll_interval_seconds: float,
    ) -> None:
        self.engine = engine
        self.poll_interval_seconds = poll_interval_seconds
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            for run in self.engine.store.list_active_runs():
                if run.state not in {
                    RunState.JOB_QUEUED,
                    RunState.JOB_RUNNING,
                }:
                    continue
                try:
                    await asyncio.to_thread(
                        self.engine.reconcile_run,
                        run.run_id,
                    )
                except Exception as exc:
                    self.engine._event(
                        run.run_id,
                        source='orchestrator',
                        event_type='job.reconciliation_failed',
                        payload={'error': str(exc)},
                    )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.poll_interval_seconds,
                )
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
