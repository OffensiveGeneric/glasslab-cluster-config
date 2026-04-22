from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from .autoresearch import (
    call_coding_notebook_agent,
    build_campaign_and_seed,
    build_decision,
    build_iteration_comparison,
    build_autoresearch_notebook,
    draft_initial_methodologies,
    ensure_follow_on_methodology_drafts,
    get_campaign_iterations,
    get_next_launchable_methodology_drafts,
    get_next_launchable_methodology_draft,
    get_required_campaign,
    methodology_to_run_request,
    summarize_campaign,
    summarize_iteration_run,
    write_autoresearch_notebook_draft,
)
from .config import Settings
from .job_submission import JobSubmitter
from .persistence import RunStore
from .registry import WorkflowRegistry
from .schemas import (
    AutoresearchCampaignCreateRequest,
    AutoresearchCampaignRecord,
    AutoresearchCampaignSummaryResponse,
    AutoresearchDecisionBatchResponse,
    AutoresearchDecisionRecord,
    AutoresearchDecisionResponse,
    AutoresearchDraftMethodologiesResponse,
    AutoresearchLaunchBatchItem,
    AutoresearchLaunchBatchResponse,
    AutoresearchIterationRecord,
    AutoresearchLaunchIterationResponse,
    AutoresearchNotebookDraftResponse,
    MethodologyDraftRecord,
    OperationRecord,
    ResearchSessionNextCommandResponse,
    RunRecord,
)
from .session_helpers import touch_research_session


def register_autoresearch_routes(
    app: FastAPI,
    *,
    settings: Settings,
    registry: WorkflowRegistry,
    store: RunStore,
    submitter: JobSubmitter,
    create_run_record: Callable[..., RunRecord],
    record_operation: Callable[..., OperationRecord],
) -> None:
    def get_required_session_campaign(session_id: str) -> AutoresearchCampaignRecord:
        session = store.get_research_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session not found')
        campaign = store.get_autoresearch_campaign(session.latest_autoresearch_campaign_id or '')
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no autoresearch campaign yet')
        return campaign

    def decide_campaign_iteration(
        campaign: AutoresearchCampaignRecord,
        iteration_id: str,
    ) -> tuple[AutoresearchCampaignRecord, AutoresearchIterationRecord, AutoresearchDecisionRecord]:
        iteration = store.get_autoresearch_iteration(iteration_id)
        if iteration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='autoresearch iteration not found')
        child_run = store.get_run(iteration.run_id)
        if child_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='run not found for iteration')
        child_summary = summarize_iteration_run(child_run, settings=settings, submitter=submitter)
        if iteration.decision is not None:
            existing = next(
                (
                    record
                    for record in store.list_autoresearch_decisions(campaign.campaign_id)
                    if record.iteration_id == iteration.iteration_id
                ),
                None,
            )
            existing_is_stale_escalation = (
                existing is not None
                and existing.decision_type == 'escalate_for_review'
                and str(child_summary.get('run_status')) == 'succeeded'
                and isinstance(child_summary.get('primary_metric_value'), (int, float))
            )
            if existing is not None and not existing_is_stale_escalation:
                return campaign, iteration, existing
            store.save_autoresearch_iteration(
                iteration.model_copy(update={'decision': None, 'status': 'completed', 'updated_at': datetime.now(timezone.utc)})
            )
            iteration = store.get_autoresearch_iteration(iteration_id) or iteration

        parent_summary = None
        baseline_iteration = None
        for prior in reversed([record for record in get_campaign_iterations(store, campaign.campaign_id) if record.iteration_id != iteration.iteration_id]):
            if prior.decision == 'keep':
                baseline_iteration = prior
                break
        if baseline_iteration is not None:
            baseline_run = store.get_run(baseline_iteration.run_id)
            if baseline_run is not None:
                parent_summary = summarize_iteration_run(baseline_run, settings=settings, submitter=submitter)
        comparison_summary = build_iteration_comparison(child_summary, parent_summary)
        decision_type, rationale = build_decision(iteration, child_summary, comparison_summary)
        decision = AutoresearchDecisionRecord(
            decision_id=uuid4().hex,
            campaign_id=campaign.campaign_id,
            iteration_id=iteration.iteration_id,
            created_at=datetime.now(timezone.utc),
            decision_type=decision_type,
            rationale=rationale,
            evidence_refs=[
                f'run:{iteration.run_id}',
                f'methodology:{iteration.child_methodology_draft_id}',
            ],
        )
        store.save_autoresearch_decision(decision)

        updated_iteration = iteration.model_copy(
            update={
                'updated_at': datetime.now(timezone.utc),
                'status': 'decided',
                'score_summary': child_summary,
                'comparison_summary': comparison_summary,
                'decision': decision_type,
            }
        )
        store.save_autoresearch_iteration(updated_iteration)

        child_draft = store.get_methodology_draft(iteration.child_methodology_draft_id)
        if child_draft is not None:
            child_draft = child_draft.model_copy(
                update={
                    'updated_at': datetime.now(timezone.utc),
                    'status': 'kept' if decision_type == 'keep' else 'discarded' if decision_type == 'discard' else 'needs_review',
                }
            )
            store.save_methodology_draft(child_draft)

        campaign_updates = {
            'updated_at': datetime.now(timezone.utc),
            'latest_decision_id': decision.decision_id,
            'latest_iteration_id': updated_iteration.iteration_id,
            'status': 'completed' if decision_type in {'keep', 'discard'} else 'needs_review',
        }
        if decision_type == 'keep':
            campaign_updates['current_best_methodology_draft_id'] = updated_iteration.child_methodology_draft_id
        updated_campaign = campaign.model_copy(update=campaign_updates)
        store.save_autoresearch_campaign(updated_campaign)
        touch_research_session(
            store,
            campaign.session_id,
            latest_autoresearch_decision_id=decision.decision_id,
            latest_autoresearch_iteration_id=updated_iteration.iteration_id,
            decision_log=[f'autoresearch decision: {decision_type}'],
        )
        return updated_campaign, updated_iteration, decision

    @app.post('/autoresearch/campaigns', response_model=AutoresearchCampaignRecord, status_code=status.HTTP_201_CREATED)
    def create_autoresearch_campaign(request: AutoresearchCampaignCreateRequest) -> AutoresearchCampaignRecord:
        campaign, _seed = build_campaign_and_seed(
            store,
            registry,
            request,
        )
        return campaign

    @app.get('/autoresearch/campaigns/latest', response_model=AutoresearchCampaignRecord)
    def get_latest_autoresearch_campaign() -> AutoresearchCampaignRecord:
        record = store.get_latest_autoresearch_campaign()
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='autoresearch campaign not found')
        return record

    @app.get('/autoresearch/campaigns/{campaign_id}', response_model=AutoresearchCampaignRecord)
    def get_autoresearch_campaign(campaign_id: str) -> AutoresearchCampaignRecord:
        return get_required_campaign(store, campaign_id)

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/draft-initial-methodologies',
        response_model=AutoresearchDraftMethodologiesResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def campaign_draft_initial_methodologies(campaign_id: str) -> AutoresearchDraftMethodologiesResponse:
        started_at = datetime.now(timezone.utc)
        campaign = get_required_campaign(store, campaign_id)
        if campaign.seed_methodology_draft_ids:
            seed = store.get_methodology_draft(campaign.seed_methodology_draft_ids[0] or '')
        else:
            seed = None
        if seed is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='campaign has no seed methodology draft')
        existing_children = [
            record for record in store.list_methodology_drafts(campaign_id) if record.parent_methodology_draft_id == seed.methodology_draft_id
        ]
        if existing_children:
            operation = record_operation(
                store,
                operation_type='autoresearch-draft-initial-methodologies',
                started_at=started_at,
                status='completed',
                session_id=campaign.session_id,
                result_detail='Initial methodology drafts already exist for this campaign.',
            )
            return AutoresearchDraftMethodologiesResponse(
                campaign=campaign,
                methodology_drafts=existing_children,
                operation=operation,
            )
        workflow = registry.get_workflow(seed.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        drafts = draft_initial_methodologies(store, campaign, seed, workflow)
        for draft in drafts:
            store.save_methodology_draft(draft)
        campaign = campaign.model_copy(
            update={
                'status': 'drafted',
                'updated_at': datetime.now(timezone.utc),
            }
        )
        store.save_autoresearch_campaign(campaign)
        touch_research_session(
            store,
            campaign.session_id,
            latest_methodology_draft_id=drafts[-1].methodology_draft_id if drafts else seed.methodology_draft_id,
        )
        operation = record_operation(
            store,
            operation_type='autoresearch-draft-initial-methodologies',
            started_at=started_at,
            status='completed',
            session_id=campaign.session_id,
            result_detail=f'Drafted {len(drafts)} initial methodology variants for campaign {campaign_id}.',
        )
        return AutoresearchDraftMethodologiesResponse(
            campaign=campaign,
            methodology_drafts=drafts,
            operation=operation,
        )

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/launch-next-iteration',
        response_model=AutoresearchLaunchIterationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def campaign_launch_next_iteration(campaign_id: str) -> AutoresearchLaunchIterationResponse:
        started_at = datetime.now(timezone.utc)
        campaign = get_required_campaign(store, campaign_id)
        try:
            draft = get_next_launchable_methodology_draft(store, campaign)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_409_CONFLICT or 'no pending methodology drafts remain' not in str(exc.detail):
                raise
            created = ensure_follow_on_methodology_drafts(
                store,
                campaign,
                registry=registry,
                settings=settings,
                submitter=submitter,
                limit=1,
            )
            if not created:
                raise
            campaign = get_required_campaign(store, campaign_id)
            draft = created[0]
        workflow = registry.get_workflow(draft.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
        run_request = methodology_to_run_request(draft, workflow)
        run = create_run_record(
            run_request,
            workflow,
            settings,
            submitter,
            store,
            source_design_id=draft.source_design_id,
            source_intake_id=draft.source_intake_id,
            run_purpose='autoresearch-validation',
            session_id=campaign.session_id,
        )
        score_summary = summarize_iteration_run(run, settings=settings, submitter=submitter)
        iteration = AutoresearchIterationRecord(
            iteration_id=uuid4().hex,
            campaign_id=campaign.campaign_id,
            parent_methodology_draft_id=draft.parent_methodology_draft_id,
            child_methodology_draft_id=draft.methodology_draft_id,
            run_id=run.run_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            status='launched',
            score_summary=score_summary,
            comparison_summary={},
            decision=None,
        )
        store.save_autoresearch_iteration(iteration)
        draft = draft.model_copy(update={'status': 'launched', 'updated_at': datetime.now(timezone.utc)})
        store.save_methodology_draft(draft)
        campaign = campaign.model_copy(
            update={
                'status': 'active',
                'updated_at': datetime.now(timezone.utc),
                'latest_iteration_id': iteration.iteration_id,
            }
        )
        store.save_autoresearch_campaign(campaign)
        touch_research_session(
            store,
            campaign.session_id,
            latest_methodology_draft_id=draft.methodology_draft_id,
            latest_autoresearch_iteration_id=iteration.iteration_id,
            latest_run_id=run.run_id,
        )
        operation = record_operation(
            store,
            operation_type='autoresearch-launch-next-iteration',
            started_at=started_at,
            status='completed',
            session_id=campaign.session_id,
            result_detail=f'Launched autoresearch iteration {iteration.iteration_id} as run {run.run_id}.',
        )
        return AutoresearchLaunchIterationResponse(
            campaign=campaign,
            methodology_draft=draft,
            iteration=iteration,
            run=run,
            operation=operation,
        )

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/launch-next-batch',
        response_model=AutoresearchLaunchBatchResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def campaign_launch_next_batch(campaign_id: str) -> AutoresearchLaunchBatchResponse:
        started_at = datetime.now(timezone.utc)
        campaign = get_required_campaign(store, campaign_id)
        try:
            drafts = get_next_launchable_methodology_drafts(store, campaign, limit=2)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_409_CONFLICT or 'no pending methodology drafts remain' not in str(exc.detail):
                raise
            drafts = ensure_follow_on_methodology_drafts(
                store,
                campaign,
                registry=registry,
                settings=settings,
                submitter=submitter,
                limit=2,
            )
            if not drafts:
                raise
            campaign = get_required_campaign(store, campaign_id)
        launches: list[AutoresearchLaunchBatchItem] = []
        latest_iteration_id = campaign.latest_iteration_id
        latest_methodology_draft_id = None
        latest_run_id = None
        for draft in drafts:
            workflow = registry.get_workflow(draft.workflow_id)
            if workflow is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
            run_request = methodology_to_run_request(draft, workflow)
            run = create_run_record(
                run_request,
                workflow,
                settings,
                submitter,
                store,
                source_design_id=draft.source_design_id,
                source_intake_id=draft.source_intake_id,
                run_purpose='autoresearch-validation',
                session_id=campaign.session_id,
            )
            score_summary = summarize_iteration_run(run, settings=settings, submitter=submitter)
            iteration = AutoresearchIterationRecord(
                iteration_id=uuid4().hex,
                campaign_id=campaign.campaign_id,
                parent_methodology_draft_id=draft.parent_methodology_draft_id,
                child_methodology_draft_id=draft.methodology_draft_id,
                run_id=run.run_id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                status='launched',
                score_summary=score_summary,
                comparison_summary={},
                decision=None,
            )
            store.save_autoresearch_iteration(iteration)
            draft = draft.model_copy(update={'status': 'launched', 'updated_at': datetime.now(timezone.utc)})
            store.save_methodology_draft(draft)
            launches.append(
                AutoresearchLaunchBatchItem(
                    methodology_draft=draft,
                    iteration=iteration,
                    run=run,
                )
            )
            latest_iteration_id = iteration.iteration_id
            latest_methodology_draft_id = draft.methodology_draft_id
            latest_run_id = run.run_id
        campaign = campaign.model_copy(
            update={
                'status': 'active',
                'updated_at': datetime.now(timezone.utc),
                'latest_iteration_id': latest_iteration_id,
            }
        )
        store.save_autoresearch_campaign(campaign)
        touch_research_session(
            store,
            campaign.session_id,
            latest_methodology_draft_id=latest_methodology_draft_id,
            latest_autoresearch_iteration_id=latest_iteration_id,
            latest_run_id=latest_run_id,
        )
        operation = record_operation(
            store,
            operation_type='autoresearch-launch-next-batch',
            started_at=started_at,
            status='completed',
            session_id=campaign.session_id,
            result_detail=f'Launched {len(launches)} autoresearch iteration(s) for campaign {campaign_id}.',
        )
        return AutoresearchLaunchBatchResponse(
            campaign=campaign,
            launches=launches,
            operation=operation,
        )

    @app.get('/autoresearch/campaigns/{campaign_id}/iterations', response_model=list[AutoresearchIterationRecord])
    def list_autoresearch_iterations(campaign_id: str) -> list[AutoresearchIterationRecord]:
        _ = get_required_campaign(store, campaign_id)
        return get_campaign_iterations(store, campaign_id)

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/decide-latest',
        response_model=AutoresearchDecisionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def decide_latest_autoresearch_iteration(campaign_id: str) -> AutoresearchDecisionResponse:
        started_at = datetime.now(timezone.utc)
        campaign = get_required_campaign(store, campaign_id)
        if not campaign.latest_iteration_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='campaign has no iterations yet')
        updated_campaign, updated_iteration, decision = decide_campaign_iteration(campaign, campaign.latest_iteration_id)
        operation = record_operation(
            store,
            operation_type='autoresearch-decide-latest',
            started_at=started_at,
            status='completed',
            session_id=campaign.session_id,
            result_detail=f"Latest autoresearch iteration was marked {decision.decision_type}.",
        )
        return AutoresearchDecisionResponse(
            campaign=updated_campaign,
            iteration=updated_iteration,
            decision=decision,
            operation=operation,
        )

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/decide-ready-batch',
        response_model=AutoresearchDecisionBatchResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def decide_ready_autoresearch_batch(campaign_id: str) -> AutoresearchDecisionBatchResponse:
        started_at = datetime.now(timezone.utc)
        campaign = get_required_campaign(store, campaign_id)
        ready_iterations: list[AutoresearchIterationRecord] = []
        for iteration in get_campaign_iterations(store, campaign_id):
            run = store.get_run(iteration.run_id)
            if run is None:
                continue
            summary = summarize_iteration_run(run, settings=settings, submitter=submitter)
            if str(summary.get('run_status')) == 'succeeded' and (
                iteration.decision is None or (
                    iteration.decision == 'escalate_for_review'
                    and isinstance(summary.get('primary_metric_value'), (int, float))
                )
            ):
                ready_iterations.append(iteration)
        if not ready_iterations:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='no completed undecided autoresearch iterations are ready')

        decisions: list[AutoresearchDecisionRecord] = []
        updated_iterations: list[AutoresearchIterationRecord] = []
        updated_campaign = campaign
        for iteration in ready_iterations:
            updated_campaign, updated_iteration, decision = decide_campaign_iteration(updated_campaign, iteration.iteration_id)
            decisions.append(decision)
            updated_iterations.append(updated_iteration)

        operation = record_operation(
            store,
            operation_type='autoresearch-decide-ready-batch',
            started_at=started_at,
            status='completed',
            session_id=campaign.session_id,
            result_detail=f"Recorded {len(decisions)} autoresearch decision(s) for campaign {campaign_id}.",
        )
        return AutoresearchDecisionBatchResponse(
            campaign=updated_campaign,
            decisions=decisions,
            iterations=updated_iterations,
            operation=operation,
        )

    @app.post(
        '/research-sessions/{session_id}/transitions/decide-autoresearch-batch',
        response_model=AutoresearchDecisionBatchResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def session_decide_autoresearch_batch(session_id: str) -> AutoresearchDecisionBatchResponse:
        campaign = get_required_session_campaign(session_id)
        return decide_ready_autoresearch_batch(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/decide-autoresearch-batch',
        response_model=AutoresearchDecisionBatchResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def latest_session_decide_autoresearch_batch() -> AutoresearchDecisionBatchResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session not found')
        return session_decide_autoresearch_batch(session.session_id)

    @app.get('/autoresearch/campaigns/{campaign_id}/summary', response_model=AutoresearchCampaignSummaryResponse)
    def get_autoresearch_campaign_summary(campaign_id: str) -> AutoresearchCampaignSummaryResponse:
        campaign = get_required_campaign(store, campaign_id)
        return summarize_campaign(store, campaign, settings=settings, submitter=submitter)

    @app.get('/autoresearch/campaigns/{campaign_id}/model-comparison', response_model=AutoresearchCampaignSummaryResponse)
    def get_autoresearch_campaign_model_comparison(campaign_id: str) -> AutoresearchCampaignSummaryResponse:
        campaign = get_required_campaign(store, campaign_id)
        return summarize_campaign(store, campaign, settings=settings, submitter=submitter)

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/draft-analysis-notebook',
        response_model=AutoresearchNotebookDraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def draft_autoresearch_analysis_notebook(campaign_id: str) -> AutoresearchNotebookDraftResponse:
        campaign = get_required_campaign(store, campaign_id)
        methodology_id = campaign.current_best_methodology_draft_id
        if methodology_id is None:
            drafts = get_campaign_iterations(store, campaign_id)
            if drafts:
                methodology_id = drafts[-1].child_methodology_draft_id
        methodology = store.get_methodology_draft(methodology_id or '')
        if methodology is None:
            drafts = store.list_methodology_drafts(campaign_id)
            if not drafts:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='campaign has no methodology drafts yet')
            methodology = drafts[-1]
        workflow = registry.get_workflow(methodology.workflow_id)
        storage_uri, notebook = write_autoresearch_notebook_draft(settings, campaign, methodology, workflow=workflow)
        return AutoresearchNotebookDraftResponse(
            campaign=campaign,
            methodology_draft=methodology,
            created_at=datetime.now(timezone.utc),
            storage_uri=storage_uri,
            notebook=notebook,
        )

    @app.post(
        '/autoresearch/campaigns/{campaign_id}/refine-analysis-notebook',
        response_model=AutoresearchNotebookDraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def refine_autoresearch_analysis_notebook(campaign_id: str) -> AutoresearchNotebookDraftResponse:
        campaign = get_required_campaign(store, campaign_id)
        methodology_id = campaign.current_best_methodology_draft_id
        if methodology_id is None:
            iterations = get_campaign_iterations(store, campaign_id)
            if iterations:
                methodology_id = iterations[-1].child_methodology_draft_id
        methodology = store.get_methodology_draft(methodology_id or '')
        if methodology is None:
            drafts = store.list_methodology_drafts(campaign_id)
            if not drafts:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='campaign has no methodology drafts yet')
            methodology = drafts[-1]
        workflow = registry.get_workflow(methodology.workflow_id)
        design = store.get_design_draft(methodology.source_design_id or '')
        interpretation = store.get_latest_interpretation()
        if interpretation is not None:
            if methodology.source_intake_id and interpretation.intake_id != methodology.source_intake_id:
                interpretation = None
            elif methodology.session_id and interpretation.session_id not in {None, methodology.session_id}:
                interpretation = None
        base_storage_uri, base_notebook = write_autoresearch_notebook_draft(settings, campaign, methodology, workflow=workflow)
        refined_notebook, warnings = call_coding_notebook_agent(
            campaign,
            methodology,
            workflow,
            base_notebook,
            settings,
            design=design,
            interpretation=interpretation,
        )
        refinement_source = 'deterministic'
        storage_uri = base_storage_uri
        notebook = base_notebook
        if refined_notebook is not None:
            storage_uri, notebook = write_autoresearch_notebook_draft(
                settings,
                campaign,
                methodology,
                workflow=workflow,
                notebook=refined_notebook,
                filename='analysis_notebook_refined.ipynb',
            )
            refinement_source = 'coding-model'
        return AutoresearchNotebookDraftResponse(
            campaign=campaign,
            methodology_draft=methodology,
            created_at=datetime.now(timezone.utc),
            storage_uri=storage_uri,
            notebook=notebook,
            refinement_source=refinement_source,
            warnings=warnings,
        )

    @app.post(
        '/research-sessions/{session_id}/transitions/start-autoresearch-campaign',
        response_model=AutoresearchCampaignRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_start_autoresearch_campaign(session_id: str) -> AutoresearchCampaignRecord:
        return create_autoresearch_campaign(AutoresearchCampaignCreateRequest(session_id=session_id))

    @app.post(
        '/research-sessions/latest/transitions/start-autoresearch-campaign',
        response_model=AutoresearchCampaignRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_start_latest_autoresearch_campaign() -> AutoresearchCampaignRecord:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_start_autoresearch_campaign(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/draft-methodologies',
        response_model=AutoresearchDraftMethodologiesResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_draft_session_methodologies(session_id: str) -> AutoresearchDraftMethodologiesResponse:
        session = store.get_research_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session not found')
        campaign = store.get_autoresearch_campaign(session.latest_autoresearch_campaign_id or '')
        if campaign is None:
            campaign = transition_start_autoresearch_campaign(session_id)
        return campaign_draft_initial_methodologies(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/draft-methodologies',
        response_model=AutoresearchDraftMethodologiesResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_draft_latest_session_methodologies() -> AutoresearchDraftMethodologiesResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_draft_session_methodologies(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/launch-autoresearch-iteration',
        response_model=AutoresearchLaunchIterationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_launch_session_autoresearch_iteration(session_id: str) -> AutoresearchLaunchIterationResponse:
        campaign = get_required_session_campaign(session_id)
        return campaign_launch_next_iteration(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/launch-autoresearch-iteration',
        response_model=AutoresearchLaunchIterationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_launch_latest_session_autoresearch_iteration() -> AutoresearchLaunchIterationResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_launch_session_autoresearch_iteration(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/launch-autoresearch-batch',
        response_model=AutoresearchLaunchBatchResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_launch_session_autoresearch_batch(session_id: str) -> AutoresearchLaunchBatchResponse:
        campaign = get_required_session_campaign(session_id)
        return campaign_launch_next_batch(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/launch-autoresearch-batch',
        response_model=AutoresearchLaunchBatchResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_launch_latest_session_autoresearch_batch() -> AutoresearchLaunchBatchResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_launch_session_autoresearch_batch(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/advance-autoresearch',
        response_model=ResearchSessionNextCommandResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_advance_session_autoresearch(session_id: str) -> ResearchSessionNextCommandResponse:
        session = store.get_research_session(session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session not found')

        campaign = store.get_autoresearch_campaign(session.latest_autoresearch_campaign_id or '')
        draft_response = None
        decide_response = None

        if campaign is None:
            draft_response = transition_draft_session_methodologies(session_id)
            campaign = get_required_session_campaign(session_id)
        else:
            try:
                decide_response = transition_decide_session_autoresearch_batch(session_id)
            except HTTPException as exc:
                if exc.status_code != status.HTTP_409_CONFLICT or str(exc.detail).strip() != 'no completed undecided autoresearch iterations are ready':
                    raise
            campaign = get_required_session_campaign(session_id)

        launch_response = transition_launch_session_autoresearch_batch(session_id)
        session = store.get_research_session(session_id) or session
        campaign = get_required_session_campaign(session_id)
        return ResearchSessionNextCommandResponse(
            session=session,
            campaign=campaign,
            draft=draft_response,
            decide=decide_response,
            launch=launch_response,
            drafted_methodology_count=len((draft_response.methodology_drafts if draft_response is not None else [])),
            decisions_recorded=len((decide_response.decisions if decide_response is not None else [])),
            launches_started=len(launch_response.launches),
        )

    @app.post(
        '/research-sessions/latest/transitions/advance-autoresearch',
        response_model=ResearchSessionNextCommandResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_advance_latest_session_autoresearch() -> ResearchSessionNextCommandResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_advance_session_autoresearch(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/decide-autoresearch-latest',
        response_model=AutoresearchDecisionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_decide_session_autoresearch_latest(session_id: str) -> AutoresearchDecisionResponse:
        campaign = get_required_session_campaign(session_id)
        return decide_latest_autoresearch_iteration(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/decide-autoresearch-latest',
        response_model=AutoresearchDecisionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_decide_latest_session_autoresearch_latest() -> AutoresearchDecisionResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_decide_session_autoresearch_latest(session.session_id)

    @app.get(
        '/research-sessions/{session_id}/autoresearch-summary',
        response_model=AutoresearchCampaignSummaryResponse,
    )
    def get_session_autoresearch_summary(session_id: str) -> AutoresearchCampaignSummaryResponse:
        campaign = get_required_session_campaign(session_id)
        return get_autoresearch_campaign_summary(campaign.campaign_id)

    @app.get(
        '/research-sessions/latest/autoresearch-summary',
        response_model=AutoresearchCampaignSummaryResponse,
    )
    def get_latest_session_autoresearch_summary() -> AutoresearchCampaignSummaryResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_autoresearch_summary(session.session_id)

    @app.get(
        '/research-sessions/{session_id}/autoresearch-model-comparison',
        response_model=AutoresearchCampaignSummaryResponse,
    )
    def get_session_autoresearch_model_comparison(session_id: str) -> AutoresearchCampaignSummaryResponse:
        campaign = get_required_session_campaign(session_id)
        return get_autoresearch_campaign_model_comparison(campaign.campaign_id)

    @app.get(
        '/research-sessions/latest/autoresearch-model-comparison',
        response_model=AutoresearchCampaignSummaryResponse,
    )
    def get_latest_session_autoresearch_model_comparison() -> AutoresearchCampaignSummaryResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return get_session_autoresearch_model_comparison(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/draft-autoresearch-notebook',
        response_model=AutoresearchNotebookDraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_draft_session_autoresearch_notebook(session_id: str) -> AutoresearchNotebookDraftResponse:
        campaign = get_required_session_campaign(session_id)
        return draft_autoresearch_analysis_notebook(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/draft-autoresearch-notebook',
        response_model=AutoresearchNotebookDraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_draft_latest_session_autoresearch_notebook() -> AutoresearchNotebookDraftResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_draft_session_autoresearch_notebook(session.session_id)

    @app.post(
        '/research-sessions/{session_id}/transitions/refine-autoresearch-notebook',
        response_model=AutoresearchNotebookDraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_refine_session_autoresearch_notebook(session_id: str) -> AutoresearchNotebookDraftResponse:
        campaign = get_required_session_campaign(session_id)
        return refine_autoresearch_analysis_notebook(campaign.campaign_id)

    @app.post(
        '/research-sessions/latest/transitions/refine-autoresearch-notebook',
        response_model=AutoresearchNotebookDraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def transition_refine_latest_session_autoresearch_notebook() -> AutoresearchNotebookDraftResponse:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        return transition_refine_session_autoresearch_notebook(session.session_id)
