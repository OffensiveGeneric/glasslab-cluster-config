from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.common.schemas import ArtifactsIndex, RunManifest, RunStatus


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str = Field(min_length=3)
    objective: str = Field(min_length=5)
    inputs: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(min_length=1)
    resource_profile: str | None = None
    run_priority: Literal['user', 'autonomous'] = 'user'
    submitted_by: str | None = None
    trace_id: str | None = None

    @field_validator('models')
    @classmethod
    def validate_unique_models(cls, value: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(value))
        if len(deduped) != len(value):
            raise ValueError('models must be unique')
        return value


class IntakeCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    raw_request: str = Field(min_length=10)
    source_refs: list[str] = Field(default_factory=list)
    document_refs: list[str] = Field(default_factory=list)
    source_type: str | None = None
    notes: list[str] = Field(default_factory=list)
    submitted_by: str | None = None
    trace_id: str | None = None

    @field_validator('source_refs', 'document_refs', 'notes')
    @classmethod
    def validate_non_empty_unique_strings(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('list entries must be unique')
        return deduped


class FreshPaperPipelineRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    paper_ref: str = Field(min_length=8)
    raw_request: str | None = None
    notes: list[str] = Field(default_factory=list)
    dataset_uri: str | None = None
    submitted_by: str | None = None
    wait_for_terminal_state: bool = True
    wait_timeout_seconds: float = Field(default=45.0, ge=1.0, le=300.0)
    poll_interval_seconds: float = Field(default=2.0, ge=0.5, le=30.0)

    @field_validator('notes')
    @classmethod
    def validate_unique_notes(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('notes entries must be unique')
        return deduped


class ResearchProblemPipelineRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    problem_statement: str = Field(min_length=12)
    max_candidate_papers: int = Field(default=3, ge=1, le=10)
    priorities: list[str] = Field(default_factory=list)
    submitted_by: str | None = None
    wait_for_terminal_state: bool = True
    wait_timeout_seconds: float = Field(default=45.0, ge=1.0, le=300.0)
    poll_interval_seconds: float = Field(default=2.0, ge=0.5, le=30.0)

    @field_validator('priorities')
    @classmethod
    def validate_unique_priorities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('priorities entries must be unique')
        return deduped


class PaperIntakeQueueCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    problem_statement: str = Field(min_length=12)
    max_candidate_papers: int = Field(default=3, ge=1, le=25)
    priorities: list[str] = Field(default_factory=list)
    submitted_by: str | None = None

    @field_validator('priorities')
    @classmethod
    def validate_unique_priorities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('priorities entries must be unique')
        return deduped


class ManualPaperCandidateCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str = Field(min_length=6)
    official_page: str | None = None
    pdf_url: str | None = None
    year: int = Field(default=2026, ge=1900, le=2100)
    venue: str = 'manual'
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    submitted_by: str | None = None

    @field_validator('notes', 'tags')
    @classmethod
    def validate_unique_manual_paper_lists(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        return list(dict.fromkeys(cleaned))


class ResearchSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str | None = None
    goal_statement: str = Field(min_length=12)
    priorities: list[str] = Field(default_factory=list)
    submitted_by: str | None = None

    @field_validator('priorities')
    @classmethod
    def validate_unique_session_priorities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('priorities entries must be unique')
        return deduped


class ResearchSessionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    session_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    title: str
    goal_statement: str
    priorities: list[str] = Field(default_factory=list)
    submitted_by: str
    working_notes: list[str] = Field(default_factory=list)
    decision_log: list[str] = Field(default_factory=list)
    next_experiment_ideas: list[str] = Field(default_factory=list)
    latest_problem_id: str | None = None
    latest_queue_id: str | None = None
    latest_document_id: str | None = None
    latest_intake_id: str | None = None
    latest_interpretation_id: str | None = None
    latest_assessment_id: str | None = None
    latest_design_id: str | None = None
    latest_run_id: str | None = None
    latest_methodology_draft_id: str | None = None
    latest_autoresearch_campaign_id: str | None = None
    latest_autoresearch_iteration_id: str | None = None
    latest_autoresearch_decision_id: str | None = None


class ResearchSessionMemoryAppendRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    working_note: str | None = None
    decision: str | None = None
    experiment_idea: str | None = None

    @field_validator('working_note', 'decision', 'experiment_idea')
    @classmethod
    def validate_optional_memory_entry(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = ' '.join(value.split()).strip()
        if not cleaned:
            raise ValueError('memory entries must not be empty')
        return cleaned


class ResearchProblemRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    problem_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    problem_statement: str
    max_candidate_papers: int = Field(default=3, ge=1, le=10)
    priorities: list[str] = Field(default_factory=list)
    submitted_by: str
    session_id: str | None = None


class IntakeRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    source_type: str
    source_refs: list[str] = Field(default_factory=list)
    document_refs: list[str] = Field(default_factory=list)
    raw_request: str
    normalized_summary: str
    workflow_family_candidates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    submitted_by: str
    session_id: str | None = None


class InterpretationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    interpretation_id: str
    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    source_type: str
    normalized_summary: str
    extracted_method_summary: str
    literature_state_summary: str
    candidate_workflow_families: list[str] = Field(default_factory=list)
    dataset_hints: list[str] = Field(default_factory=list)
    evaluation_targets: list[str] = Field(default_factory=list)
    extracted_claims: list[str] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)
    bounded_experiment_ideas: list[str] = Field(default_factory=list)
    recommended_method_family: str | None = None
    recommended_datasets: list[str] = Field(default_factory=list)
    recommended_metrics: list[str] = Field(default_factory=list)
    recommended_baselines: list[str] = Field(default_factory=list)
    recommended_architectures: list[str] = Field(default_factory=list)
    recommended_python_packages: list[str] = Field(default_factory=list)
    preferred_workflow_id: str | None = None
    preferred_resource_profile: str | None = None
    gpu_required: bool = False
    mutation_axes: list[str] = Field(default_factory=list)
    interpretation_source: str = 'deterministic'
    interpretation_backend: dict[str, Any] | None = None
    interpretation_warnings: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    submitted_by: str
    session_id: str | None = None


class ReplicabilityAssessmentRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    assessment_id: str
    interpretation_id: str
    intake_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    recommendation: str
    recommended_workflow_id: str | None = None
    candidate_workflow_families: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    approval_tier: str | None = None
    assessment_notes: list[str] = Field(default_factory=list)
    submitted_by: str
    session_id: str | None = None


class DesignDraftRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    design_id: str
    intake_id: str
    source_assessment_id: str | None = None
    created_at: datetime
    updated_at: datetime
    status: str
    workflow_id: str
    workflow_family: str
    objective: str
    declared_inputs: dict[str, Any] = Field(default_factory=dict)
    unresolved_inputs: list[str] = Field(default_factory=list)
    candidate_models: list[str] = Field(default_factory=list)
    resource_profile: str
    expected_artifacts: dict[str, list[str]]
    approval_tier: str
    design_notes: list[str] = Field(default_factory=list)
    submitted_by: str
    session_id: str | None = None


class MethodologyDraftRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    methodology_draft_id: str
    campaign_id: str
    session_id: str
    source_intake_id: str | None = None
    source_design_id: str | None = None
    parent_methodology_draft_id: str | None = None
    created_at: datetime
    updated_at: datetime
    objective: str
    hypothesis: str
    method_family: str
    datasets: list[str] = Field(default_factory=list)
    architectures: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    bounded_experimentability: str
    status: Literal['seed', 'ready_for_execution', 'launched', 'kept', 'discarded', 'needs_review']
    workflow_id: str
    workflow_family: str
    declared_inputs: dict[str, Any] = Field(default_factory=dict)
    candidate_models: list[str] = Field(default_factory=list)
    resource_profile: str
    approval_tier: str
    mutation_diff: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class AutoresearchCampaignRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign_id: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal['created', 'drafted', 'active', 'needs_review', 'completed']
    objective: str
    source_design_id: str | None = None
    seed_methodology_draft_ids: list[str] = Field(default_factory=list)
    current_best_methodology_draft_id: str | None = None
    latest_iteration_id: str | None = None
    latest_decision_id: str | None = None
    max_iterations: int = Field(default=3, ge=1, le=25)
    evaluation_policy: str
    mutation_policy: str
    notes: list[str] = Field(default_factory=list)


class AutoresearchIterationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    iteration_id: str
    campaign_id: str
    parent_methodology_draft_id: str | None = None
    child_methodology_draft_id: str
    run_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal['launched', 'completed', 'decided', 'needs_review']
    score_summary: dict[str, Any] = Field(default_factory=dict)
    comparison_summary: dict[str, Any] = Field(default_factory=dict)
    decision: Literal['keep', 'discard', 'escalate_for_review'] | None = None


class AutoresearchDecisionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    decision_id: str
    campaign_id: str
    iteration_id: str
    created_at: datetime
    decision_type: Literal['keep', 'discard', 'escalate_for_review']
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)


class DesignDraftReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    resolved_inputs: dict[str, Any] = Field(default_factory=dict)
    review_notes: list[str] = Field(default_factory=list)

    @field_validator('review_notes')
    @classmethod
    def validate_unique_review_notes(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('review_notes entries must be unique')
        return deduped


class DigestScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    cron_expr: str = Field(min_length=5)
    digest_kind: str = Field(min_length=3)
    scope_filter: dict[str, Any] = Field(default_factory=dict)
    owner: str | None = None


class ApprovedRerunScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    cron_expr: str = Field(min_length=5)
    owner: str | None = None


class ScheduledOperationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schedule_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    operation_type: str
    approval_tier: str
    owner: str
    cron_expr: str
    scope_filter: dict[str, Any] = Field(default_factory=dict)
    digest_kind: str | None = None
    source_design_id: str | None = None
    source_run_id: str | None = None
    workflow_id: str | None = None
    allowed_dataset_uri: str | None = None
    allowed_model_ids: list[str] = Field(default_factory=list)
    allowed_runner_image: str | None = None
    resource_profile: str | None = None
    last_execution_at: datetime | None = None
    last_result_status: str | None = None
    last_result_detail: str | None = None


class ScheduledExecutionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    execution_id: str
    schedule_id: str
    operation_type: str
    started_at: datetime
    finished_at: datetime
    result_status: str
    result_detail: str
    produced_run_ids: list[str] = Field(default_factory=list)
    digest_payload: dict[str, Any] = Field(default_factory=dict)


class OperationRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    operation_id: str
    operation_type: str
    status: Literal['completed', 'failed']
    started_at: datetime
    finished_at: datetime
    session_id: str | None = None
    queue_id: str | None = None
    document_id: str | None = None
    intake_id: str | None = None
    result_detail: str
    error_detail: str | None = None


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    field: str
    message: str


class JobSubmissionReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_name: str
    namespace: str
    accepted_at: datetime
    status: str
    detail: str


class WorkflowFamilySummary(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str
    display_name: str
    workflow_family: str
    description: str
    allowed_models: list[str]
    resource_profile: str
    approval_tier: str
    execution_status: str
    submission_backend: str
    execution_blockers: list[str] = Field(default_factory=list)


class ExecutionPreflightResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workflow_id: str
    runner_image: str
    resource_profile: str
    resource_requests: dict[str, str] = Field(default_factory=dict)
    resource_limits: dict[str, str] = Field(default_factory=dict)
    node_selector: dict[str, str] = Field(default_factory=dict)
    job_submission_mode: str
    execution_status: str
    submission_backend: str
    runtime_requirements: dict[str, Any] = Field(default_factory=dict)
    ready: bool
    eligible_nodes: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RunRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    workflow_id: str
    created_at: datetime
    updated_at: datetime
    manifest: RunManifest
    status: RunStatus
    job_submission: JobSubmissionReceipt
    source_design_id: str | None = None
    source_intake_id: str | None = None
    run_purpose: str | None = None
    run_priority: Literal['user', 'autonomous'] = 'user'
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    session_id: str | None = None


class PaperPipelineReportState(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str | None = None
    run_status: str
    terminal: bool
    report_available: bool
    report_path: str | None = None
    artifact_count: int = 0
    artifact_names: list[str] = Field(default_factory=list)


class ResearchProblemPaperCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    paper_id: str
    title: str
    year: int
    venue: str
    venue_id: str | None = None
    priority: str
    tracks: list[str] = Field(default_factory=list)
    bounded_job_fit: int
    replication_complexity: int
    official_page: str | None = None
    pdf_url: str | None = None
    abstract_excerpt: str | None = None
    why_seed: str
    first_jobs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    match_score: int = 0
    match_reasons: list[str] = Field(default_factory=list)


class PaperIntakeCandidateRecord(ResearchProblemPaperCandidate):
    model_config = ConfigDict(extra='forbid')

    intake_status: Literal['pending', 'staged'] = 'pending'
    staged_intake_id: str | None = None


class PaperIntakeQueueRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    queue_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal['ready', 'exhausted'] = 'ready'
    problem_statement: str
    selected_tracks: list[str] = Field(default_factory=list)
    selected_queries: list[str] = Field(default_factory=list)
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    candidates: list[PaperIntakeCandidateRecord] = Field(default_factory=list)
    submitted_by: str
    session_id: str | None = None


class SourceDocumentRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    document_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal['fetched', 'fetch-failed']
    source_url: str
    submitted_by: str
    storage_uri: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    title: str | None = None
    text_excerpt: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract_excerpt: str | None = None
    method_hints: list[str] = Field(default_factory=list)
    dataset_hints: list[str] = Field(default_factory=list)
    loss_hints: list[str] = Field(default_factory=list)
    architecture_hints: list[str] = Field(default_factory=list)
    baseline_hints: list[str] = Field(default_factory=list)
    metric_hints: list[str] = Field(default_factory=list)
    domain_task_hints: list[str] = Field(default_factory=list)
    python_library_hints: list[str] = Field(default_factory=list)
    expected_title: str | None = None
    validation_status: Literal['unknown', 'matched', 'mismatch'] = 'unknown'
    validation_notes: list[str] = Field(default_factory=list)
    fetch_error: str | None = None
    session_id: str | None = None


class ResearchSessionContextResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    session: ResearchSessionRecord
    research_problem: ResearchProblemRecord | None = None
    paper_intake_queue: PaperIntakeQueueRecord | None = None
    source_document: SourceDocumentRecord | None = None
    intake: IntakeRecord | None = None
    interpretation: InterpretationRecord | None = None
    assessment: ReplicabilityAssessmentRecord | None = None
    design: DesignDraftRecord | None = None
    run: RunRecord | None = None


class LiteratureDigestResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    session_id: str
    source_documents: list[SourceDocumentRecord] = Field(default_factory=list)
    matched_document_count: int = 0
    mismatched_document_count: int = 0
    fetch_failed_document_count: int = 0
    top_methods: list[str] = Field(default_factory=list)
    top_datasets: list[str] = Field(default_factory=list)
    top_losses: list[str] = Field(default_factory=list)
    top_architectures: list[str] = Field(default_factory=list)
    top_baselines: list[str] = Field(default_factory=list)
    top_metrics: list[str] = Field(default_factory=list)
    top_domain_tasks: list[str] = Field(default_factory=list)
    notable_titles: list[str] = Field(default_factory=list)
    summary_notes: list[str] = Field(default_factory=list)


class ResearchSessionBootstrapStatusResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    active_session: ResearchSessionRecord | None = None
    staged_research_problem: ResearchProblemRecord | None = None
    recommended_next_action: Literal[
        'create-session-manually',
        'create-session-from-latest-problem',
        'apply-session-skills',
    ]
    can_create_session_from_latest_problem: bool = False
    can_apply_session_skills: bool = False
    detail: str


class ResearchSessionBootstrapResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    bootstrap_action: Literal[
        'reuse-active-session',
        'created-session-from-latest-problem',
        'create-session-manually',
    ]
    session: ResearchSessionRecord | None = None
    staged_research_problem: ResearchProblemRecord | None = None
    detail: str


class StartLiteratureSearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    goal_statement: str | None = None
    priorities: list[str] = Field(default_factory=list)
    submitted_by: str | None = None

    @field_validator('goal_statement')
    @classmethod
    def validate_optional_goal_statement(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = ' '.join(value.split()).strip()
        if not cleaned:
            raise ValueError('goal_statement must not be empty')
        if len(cleaned) < 12:
            raise ValueError('goal_statement must be at least 12 characters')
        return cleaned

    @field_validator('priorities')
    @classmethod
    def validate_unique_start_priorities(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) != len(cleaned):
            raise ValueError('priorities entries must be unique')
        return deduped


class StartLiteratureSearchResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    action: str
    session: ResearchSessionRecord
    research_problem: ResearchProblemRecord
    paper_intake_queue: PaperIntakeQueueRecord
    operation: OperationRecord


class AutoresearchCampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    session_id: str | None = None
    source_design_id: str | None = None
    objective: str | None = None
    max_iterations: int = Field(default=3, ge=1, le=25)
    evaluation_policy: str = 'metrics-first-v1'
    mutation_policy: str = 'methodology-variants-v1'
    notes: list[str] = Field(default_factory=list)

    @field_validator('notes')
    @classmethod
    def validate_unique_campaign_notes(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        return list(dict.fromkeys(cleaned))


class AutoresearchDraftMethodologiesResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign: AutoresearchCampaignRecord
    methodology_drafts: list[MethodologyDraftRecord] = Field(default_factory=list)
    operation: OperationRecord


class AutoresearchLaunchIterationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign: AutoresearchCampaignRecord
    methodology_draft: MethodologyDraftRecord
    iteration: AutoresearchIterationRecord
    run: RunRecord
    operation: OperationRecord


class AutoresearchDecisionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign: AutoresearchCampaignRecord
    iteration: AutoresearchIterationRecord
    decision: AutoresearchDecisionRecord
    operation: OperationRecord


class AutoresearchCampaignSummaryResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign: AutoresearchCampaignRecord
    methodology_drafts: list[MethodologyDraftRecord] = Field(default_factory=list)
    iterations: list[AutoresearchIterationRecord] = Field(default_factory=list)
    decisions: list[AutoresearchDecisionRecord] = Field(default_factory=list)
    best_methodology_draft: MethodologyDraftRecord | None = None
    latest_run: RunRecord | None = None
    proposed_next_variants: list[str] = Field(default_factory=list)


class AutoresearchNotebookDraftResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    campaign: AutoresearchCampaignRecord
    methodology_draft: MethodologyDraftRecord
    created_at: datetime
    storage_uri: str
    notebook: dict[str, Any]
    refinement_source: Literal['deterministic', 'coding-model'] = 'deterministic'
    warnings: list[str] = Field(default_factory=list)


class FreshPaperPipelineResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    intake: IntakeRecord
    interpretation: InterpretationRecord
    assessment: ReplicabilityAssessmentRecord
    design: DesignDraftRecord
    run: RunRecord | None = None
    report_state: PaperPipelineReportState
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class ResearchProblemPipelineResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    problem_statement: str
    selected_tracks: list[str] = Field(default_factory=list)
    selected_queries: list[str] = Field(default_factory=list)
    selected_papers: list[ResearchProblemPaperCandidate] = Field(default_factory=list)
    chosen_paper_id: str | None = None
    pipeline: FreshPaperPipelineResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class LogEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')

    timestamp: datetime
    level: str
    message: str
    payload: dict[str, Any] | None = None


class RunArtifactsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    artifacts: ArtifactsIndex


class RunLogsResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    run_id: str
    logs: list[LogEntry]
