from __future__ import annotations

import json
import os
from urllib import request as urllib_request

from fastapi import FastAPI

from .models import HealthResponse, RunOnceResponse, ScheduledExecutionPayload, WorkerConfigMetadata

WORKFLOW_API_URL = os.environ.get(
    'GLASSLAB_SCHEDULE_WORKER_WORKFLOW_API_URL',
    'http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080',
).rstrip('/')
TIMEOUT_SECONDS = float(os.environ.get('GLASSLAB_SCHEDULE_WORKER_TIMEOUT_SECONDS', '30'))


def worker_config() -> WorkerConfigMetadata:
    return WorkerConfigMetadata(
        workflow_api_url=WORKFLOW_API_URL,
        timeout_seconds=TIMEOUT_SECONDS,
    )


def run_due_digest_cycle() -> RunOnceResponse:
    request_obj = urllib_request.Request(
        f'{WORKFLOW_API_URL}/digest-schedules/run-due',
        data=b'',
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib_request.urlopen(request_obj, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode('utf-8'))
    executions = [ScheduledExecutionPayload.model_validate(item) for item in payload]
    return RunOnceResponse(
        worker_status='ok',
        executed_count=len(executions),
        executions=executions,
        worker_config=worker_config(),
    )


app = FastAPI(title='glasslab-schedule-worker', version='0.1.0')


@app.get('/healthz', response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status='ok', worker_config=worker_config())


@app.post('/run-once', response_model=RunOnceResponse)
def run_once() -> RunOnceResponse:
    return run_due_digest_cycle()
