from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, HTTPException, status

from .config import Settings
from .execution_preflight import build_execution_preflight_result
from .job_submission import JobSubmitter
from .persistence import RunStore
from .registry import WorkflowRegistry
from .run_artifacts import load_artifacts_from_disk, load_logs_from_disk, resolve_run_status
from .schemas import ExecutionPreflightResult, RunArtifactsResponse, RunCreateRequest, RunLogsResponse, RunRecord, WorkflowFamilySummary


def register_execution_routes(
    app: FastAPI,
    *,
    settings: Settings,
    registry: WorkflowRegistry,
    store: RunStore,
    submitter: JobSubmitter,
    create_run_record: Callable[..., RunRecord],
) -> None:
    def get_required_session_design(session_id: str):
        session = store.get_research_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session not found')
        design = store.get_design_draft(session.latest_design_id or '')
        if design is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no design draft yet')
        return design

    def enrich_preflight_with_interpretation(
        preflight: ExecutionPreflightResult,
        *,
        design,
        session_id: str,
        intake_id: str,
        workflow_id: str,
        resource_profile: str,
    ) -> ExecutionPreflightResult:
        warnings = list(preflight.warnings)
        blocking_issues = list(preflight.blocking_issues)
        declared_inputs = dict(getattr(design, 'declared_inputs', {}) or {})

        train_uri = str(declared_inputs.get('train_uri', '')).strip()
        test_uri = str(declared_inputs.get('test_uri', '')).strip()
        validation_uri = str(declared_inputs.get('validation_uri', '')).strip()
        validation_strategy = str(declared_inputs.get('validation_strategy', '')).strip()
        validation_split = str(declared_inputs.get('validation_split', '')).strip()

        if train_uri and test_uri and train_uri == test_uri:
            blocking_issues.append('train_uri and test_uri resolve to the same dataset path; this risks direct overfitting')
        if not validation_uri and not validation_strategy and not validation_split:
            warnings.append(
                'no explicit validation split or validation strategy is declared; overfitting checks may be weak even if a test split exists'
            )
        elif validation_split:
            warnings.append(f'declared validation split: {validation_split}')
        elif validation_strategy:
            warnings.append(f'declared validation strategy: {validation_strategy}')
        elif validation_uri:
            warnings.append('declared dedicated validation dataset split is present')

        interpretation = store.get_latest_interpretation()
        if interpretation is None:
            return preflight.model_copy(update={'warnings': warnings, 'blocking_issues': blocking_issues})
        if interpretation.intake_id != intake_id:
            return preflight.model_copy(update={'warnings': warnings, 'blocking_issues': blocking_issues})
        if interpretation.session_id not in {None, session_id}:
            return preflight.model_copy(update={'warnings': warnings, 'blocking_issues': blocking_issues})
        required_python_packages = [
            str(item) for item in preflight.runtime_requirements.get('required_python_packages', [])
        ]
        recommended_python_packages = [str(item) for item in interpretation.recommended_python_packages]
        if required_python_packages and recommended_python_packages:
            missing_from_runtime = [
                package for package in recommended_python_packages if package not in required_python_packages
            ]
            if missing_from_runtime:
                warnings.append(
                    'interpretation recommends Python packages outside the declared workflow runtime: '
                    + ', '.join(missing_from_runtime)
                )
            else:
                warnings.append(
                    'interpretation-recommended Python packages fit the declared workflow runtime: '
                    + ', '.join(recommended_python_packages)
                )
        if interpretation.preferred_workflow_id and interpretation.preferred_workflow_id != workflow_id:
            warnings.append(
                f'interpretation preferred workflow {interpretation.preferred_workflow_id} '
                f'but session design selected {workflow_id}'
            )
        if interpretation.preferred_resource_profile and interpretation.preferred_resource_profile != resource_profile:
            warnings.append(
                f'interpretation preferred resource profile {interpretation.preferred_resource_profile} '
                f'but session design selected {resource_profile}'
            )
        workflow_requires_gpu = bool(preflight.runtime_requirements.get('gpu'))
        if interpretation.gpu_required and not workflow_requires_gpu:
            warnings.append('interpretation indicates GPU is required but selected workflow runtime does not declare GPU support')
        if interpretation.dataset_hints:
            warnings.append('interpretation dataset hints: ' + ', '.join(interpretation.dataset_hints[:3]))
        if interpretation.evaluation_targets:
            warnings.append('interpretation evaluation targets: ' + ', '.join(interpretation.evaluation_targets[:3]))
        return preflight.model_copy(update={'warnings': warnings, 'blocking_issues': blocking_issues})

    @app.get('/workflow-families', response_model=list[WorkflowFamilySummary])
    def list_workflow_families() -> list[WorkflowFamilySummary]:
        return [
            WorkflowFamilySummary(
                workflow_id=entry.workflow_id,
                display_name=entry.display_name,
                workflow_family=entry.workflow_family,
                description=entry.description,
                allowed_models=entry.allowed_models,
                resource_profile=entry.resource_profile.profile_name,
                approval_tier=entry.approval_tier,
                execution_status=entry.execution_status,
                submission_backend=entry.submission_backend,
                execution_blockers=entry.execution_blockers,
            )
            for entry in registry.list_workflows()
        ]

    @app.get('/workflow-families/{workflow_id}/execution-preflight', response_model=ExecutionPreflightResult)
    def get_workflow_execution_preflight(workflow_id: str) -> ExecutionPreflightResult:
        workflow = registry.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='workflow not found')
        return build_execution_preflight_result(workflow, settings)

    @app.post('/runs', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run(request: RunCreateRequest) -> RunRecord:
        workflow = registry.get_workflow(request.workflow_id)
        if workflow is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[{'field': 'workflow_id', 'message': f'unsupported workflow family: {request.workflow_id}'}],
        )
        return create_run_record(request, workflow, settings, submitter, store)

    @app.get('/research-sessions/latest/execution-preflight', response_model=ExecutionPreflightResult)
    def get_latest_session_execution_preflight() -> ExecutionPreflightResult:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_execution_preflight(session.session_id)

    @app.post('/research-sessions/latest/runs/from-design', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run_from_latest_session_design() -> RunRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return create_run_from_session_design(session.session_id)

    @app.get('/research-sessions/{session_id}/execution-preflight', response_model=ExecutionPreflightResult)
    def get_session_execution_preflight(session_id: str) -> ExecutionPreflightResult:
        design = get_required_session_design(session_id)
        workflow = registry.get_workflow(design.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        preflight = build_execution_preflight_result(workflow, settings)
        return enrich_preflight_with_interpretation(
            preflight,
            design=design,
            session_id=session_id,
            intake_id=design.intake_id,
            workflow_id=design.workflow_id,
            resource_profile=design.resource_profile,
        )

    @app.post('/research-sessions/{session_id}/runs/from-design', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run_from_session_design(session_id: str) -> RunRecord:
        design = get_required_session_design(session_id)
        if design.status != 'ready_for_run':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='design draft is not ready_for_run')
        workflow = registry.get_workflow(design.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        request = RunCreateRequest(
            workflow_id=design.workflow_id,
            objective=design.objective,
            inputs=design.declared_inputs,
            models=design.candidate_models or workflow.allowed_models[:1],
            resource_profile=design.resource_profile,
            submitted_by=design.submitted_by,
        )
        return create_run_record(
            request,
            workflow,
            settings,
            submitter,
            store,
            source_design_id=design.design_id,
            source_intake_id=design.intake_id,
            run_purpose='validation',
            session_id=design.session_id,
        )

    @app.post('/runs/from-latest-design-draft', response_model=RunRecord, status_code=status.HTTP_201_CREATED)
    def create_run_from_latest_design_draft() -> RunRecord:
        design = store.get_latest_design_draft()
        if design is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        if design.status != 'ready_for_run':
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='design draft is not ready_for_run')
        workflow = registry.get_workflow(design.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        request = RunCreateRequest(
            workflow_id=design.workflow_id,
            objective=design.objective,
            inputs=design.declared_inputs,
            models=design.candidate_models or workflow.allowed_models[:1],
            resource_profile=design.resource_profile,
            submitted_by=design.submitted_by,
        )
        return create_run_record(
            request,
            workflow,
            settings,
            submitter,
            store,
            source_design_id=design.design_id,
            source_intake_id=design.intake_id,
            run_purpose='validation',
            session_id=design.session_id,
        )

    @app.get('/runs/{run_id}', response_model=RunRecord)
    def get_run(run_id: str) -> RunRecord:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        return record.model_copy(update={'status': resolve_run_status(record, settings, submitter)})

    @app.get('/runs/{run_id}/artifacts', response_model=RunArtifactsResponse)
    def get_run_artifacts(run_id: str) -> RunArtifactsResponse:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        artifacts = load_artifacts_from_disk(settings, run_id) or store.get_artifacts(run_id)
        if artifacts is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='artifacts not found')
        return RunArtifactsResponse(run_id=run_id, artifacts=artifacts)

    @app.get('/runs/{run_id}/logs', response_model=RunLogsResponse)
    def get_run_logs(run_id: str) -> RunLogsResponse:
        record = store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found')
        logs = load_logs_from_disk(settings, run_id)
        if not logs:
            logs = submitter.get_live_logs(record) or store.get_logs(run_id)
        return RunLogsResponse(run_id=run_id, logs=logs)
