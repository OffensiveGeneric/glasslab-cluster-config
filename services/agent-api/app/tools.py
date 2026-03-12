from __future__ import annotations

from . import registry
from .job_status import JobStatusService
from .job_submitter import JobSubmitter
from .schemas import PlannerSpec
from .state_store import StateStore
from .summarizer import ResultSummarizer
from .validator import validate_spec as validate_planner_spec


def list_pipelines() -> list[dict]:
    return registry.list_pipelines()


def list_datasets() -> list[dict]:
    return registry.list_datasets()


def validate_spec(spec: PlannerSpec | dict):
    return validate_planner_spec(spec)


def submit_job(job_submitter: JobSubmitter, spec: PlannerSpec, experiment_id: str, trace_id: str):
    return job_submitter.submit_job(spec=spec, experiment_id=experiment_id, trace_id=trace_id)


def get_job_status(job_status_service: JobStatusService, job_id: str) -> dict:
    return job_status_service.get_job_status(job_id)


def get_run_summary(state_store: StateStore, experiment_id: str) -> str | None:
    record = state_store.get_experiment(experiment_id)
    return None if record is None else record.result_summary


def summarize_result(summarizer: ResultSummarizer, result_payload: dict) -> str:
    return summarizer.summarize_result(result_payload)
