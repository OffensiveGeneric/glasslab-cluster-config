from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import HTTPException, status

from services.common.schemas import WorkflowRegistryEntry

from .config import Settings
from .job_submission import JobSubmitter
from .persistence import RunStore
from .registry import WorkflowRegistry
from .run_artifacts import artifact_run_dir, resolve_run_status
from .schemas import AutoresearchCampaignCreateRequest, AutoresearchCampaignRecord, AutoresearchCampaignSummaryResponse, AutoresearchDecisionRecord, AutoresearchIterationRecord, DesignDraftRecord, InterpretationRecord, MethodologyDraftRecord, RunCreateRequest, RunRecord
from .session_helpers import get_required_research_session, touch_research_session


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([value.strip() for value in values if value and value.strip()]))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _find_latest_design_for_campaign(
    store: RunStore,
    *,
    session_id: str,
    source_design_id: str | None,
) -> DesignDraftRecord:
    if source_design_id:
        design = store.get_design_draft(source_design_id)
        if design is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='design draft not found')
        return design
    session = get_required_research_session(store, session_id)
    design = store.get_design_draft(session.latest_design_id or '')
    if design is None:
        design = store.get_latest_design_draft()
    if design is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='research session has no design draft yet')
    return design


def _methodology_family_for_workflow(workflow_id: str) -> str:
    if workflow_id == 'generic-tabular-benchmark':
        return 'tabular-methodology-validation'
    if workflow_id == 'gpu-experiment':
        return 'gpu-methodology-validation'
    return 'bounded-methodology-validation'


def _extract_metric_hints(design: DesignDraftRecord) -> list[str]:
    metrics: list[str] = []
    joined_notes = ' '.join(design.design_notes).lower()
    for metric in ['accuracy', 'f1', 'roc_auc', 'precision', 'recall', 'rmse']:
        if metric in joined_notes:
            metrics.append(metric)
    if not metrics:
        metrics.append('accuracy')
    return _dedupe(metrics)


def _extract_dataset_hints(design: DesignDraftRecord) -> list[str]:
    candidates = [
        str(design.declared_inputs.get('dataset_name', '')).strip(),
        str(design.declared_inputs.get('dataset_uri', '')).strip(),
    ]
    return _dedupe(candidates)


def _extract_risks(design: DesignDraftRecord) -> list[str]:
    risks = [note for note in design.design_notes if 'risk' in note.lower() or 'unresolved' in note.lower()]
    if design.unresolved_inputs:
        risks.append('Unresolved design inputs remain.')
    if not risks:
        risks.append('Keep methodology within approved workflow bounds.')
    return _dedupe(risks)


def _seed_models_for_design(design: DesignDraftRecord, workflow: WorkflowRegistryEntry) -> list[str]:
    return _dedupe(design.candidate_models or workflow.allowed_models[:2])


def build_seed_methodology_draft(
    campaign: AutoresearchCampaignRecord,
    design: DesignDraftRecord,
    workflow: WorkflowRegistryEntry,
) -> MethodologyDraftRecord:
    now = _now()
    models = _seed_models_for_design(design, workflow)
    objective = campaign.objective or design.objective
    return MethodologyDraftRecord(
        methodology_draft_id=uuid4().hex,
        campaign_id=campaign.campaign_id,
        session_id=campaign.session_id,
        source_intake_id=design.intake_id,
        source_design_id=design.design_id,
        parent_methodology_draft_id=None,
        created_at=now,
        updated_at=now,
        objective=objective,
        hypothesis='A bounded validation run can reproduce the design intent on the approved template.',
        method_family=_methodology_family_for_workflow(workflow.workflow_id),
        datasets=_extract_dataset_hints(design),
        architectures=models,
        baselines=models[:1],
        metrics=_extract_metric_hints(design),
        risks=_extract_risks(design),
        bounded_experimentability='approved-template-fit',
        status='seed',
        workflow_id=workflow.workflow_id,
        workflow_family=workflow.workflow_family,
        declared_inputs=design.declared_inputs,
        candidate_models=models,
        resource_profile=design.resource_profile,
        approval_tier=design.approval_tier,
        mutation_diff={},
        notes=['seed draft from approved design'],
    )


def _build_variant_specs(seed: MethodologyDraftRecord, workflow: WorkflowRegistryEntry) -> list[dict[str, Any]]:
    models = _dedupe(seed.candidate_models or workflow.allowed_models)
    if not models:
        models = workflow.allowed_models[:1]
    specs: list[dict[str, Any]] = []
    if models:
        specs.append(
            {
                'candidate_models': [models[0]],
                'architectures': [models[0]],
                'baselines': [models[0]],
                'metrics': list(seed.metrics),
                'hypothesis': f'{models[0]} provides a stable bounded baseline on the approved dataset split.',
                'mutation_diff': {'model_family': {'from': models, 'to': [models[0]]}},
                'notes': ['single-model baseline variant'],
            }
        )
    if len(models) >= 2:
        specs.append(
            {
                'candidate_models': [models[1]],
                'architectures': [models[1]],
                'baselines': [models[0]],
                'metrics': list(seed.metrics),
                'hypothesis': f'{models[1]} may outperform the baseline under the same approved template.',
                'mutation_diff': {'model_family': {'from': [models[0]], 'to': [models[1]]}},
                'notes': ['alternative model variant'],
            }
        )
        specs.append(
            {
                'candidate_models': models[:2],
                'architectures': models[:2],
                'baselines': [models[0]],
                'metrics': list(seed.metrics) + ['accuracy'],
                'hypothesis': 'A side-by-side bounded comparison of the top approved models will clarify the better default.',
                'mutation_diff': {
                    'baseline_inclusion': {'enabled': True},
                    'model_family': {'from': [models[0]], 'to': models[:2]},
                },
                'notes': ['pairwise comparison variant'],
            }
        )
    return specs[:3]


def draft_initial_methodologies(
    campaign: AutoresearchCampaignRecord,
    seed: MethodologyDraftRecord,
    workflow: WorkflowRegistryEntry,
) -> list[MethodologyDraftRecord]:
    drafts: list[MethodologyDraftRecord] = []
    for spec in _build_variant_specs(seed, workflow):
        now = _now()
        drafts.append(
            MethodologyDraftRecord(
                methodology_draft_id=uuid4().hex,
                campaign_id=campaign.campaign_id,
                session_id=campaign.session_id,
                source_intake_id=seed.source_intake_id,
                source_design_id=seed.source_design_id,
                parent_methodology_draft_id=seed.methodology_draft_id,
                created_at=now,
                updated_at=now,
                objective=seed.objective,
                hypothesis=spec['hypothesis'],
                method_family=seed.method_family,
                datasets=list(seed.datasets),
                architectures=spec['architectures'],
                baselines=spec['baselines'],
                metrics=_dedupe(spec['metrics']),
                risks=list(seed.risks),
                bounded_experimentability='approved-template-fit',
                status='ready_for_execution',
                workflow_id=seed.workflow_id,
                workflow_family=seed.workflow_family,
                declared_inputs=dict(seed.declared_inputs),
                candidate_models=spec['candidate_models'],
                resource_profile=seed.resource_profile,
                approval_tier=seed.approval_tier,
                mutation_diff=spec['mutation_diff'],
                notes=spec['notes'],
            )
        )
    return drafts


def build_autoresearch_campaign(
    request: AutoresearchCampaignCreateRequest,
    *,
    session_id: str,
    source_design_id: str,
    objective: str,
) -> AutoresearchCampaignRecord:
    now = _now()
    return AutoresearchCampaignRecord(
        campaign_id=uuid4().hex,
        session_id=session_id,
        created_at=now,
        updated_at=now,
        status='created',
        objective=objective,
        source_design_id=source_design_id,
        seed_methodology_draft_ids=[],
        current_best_methodology_draft_id=None,
        latest_iteration_id=None,
        latest_decision_id=None,
        max_iterations=request.max_iterations,
        evaluation_policy=request.evaluation_policy,
        mutation_policy=request.mutation_policy,
        notes=list(request.notes),
    )


def methodology_to_run_request(draft: MethodologyDraftRecord) -> RunCreateRequest:
    return RunCreateRequest(
        workflow_id=draft.workflow_id,
        objective=draft.objective,
        inputs=draft.declared_inputs,
        models=draft.candidate_models or draft.architectures or draft.baselines,
        resource_profile=draft.resource_profile,
        run_priority='autonomous',
        submitted_by='glasslab-autoresearch',
    )


def get_required_campaign(store: RunStore, campaign_id: str) -> AutoresearchCampaignRecord:
    campaign = store.get_autoresearch_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='autoresearch campaign not found')
    return campaign


def get_campaign_methodology_drafts(store: RunStore, campaign_id: str) -> list[MethodologyDraftRecord]:
    return store.list_methodology_drafts(campaign_id)


def get_campaign_iterations(store: RunStore, campaign_id: str) -> list[AutoresearchIterationRecord]:
    return store.list_autoresearch_iterations(campaign_id)


def get_campaign_decisions(store: RunStore, campaign_id: str) -> list[AutoresearchDecisionRecord]:
    return store.list_autoresearch_decisions(campaign_id)


def get_next_launchable_methodology_draft(
    store: RunStore,
    campaign: AutoresearchCampaignRecord,
) -> MethodologyDraftRecord:
    iterations = store.list_autoresearch_iterations(campaign.campaign_id)
    launched_ids = {record.child_methodology_draft_id for record in iterations}
    drafts = [
        draft
        for draft in store.list_methodology_drafts(campaign.campaign_id)
        if draft.status == 'ready_for_execution' and draft.methodology_draft_id not in launched_ids
    ]
    drafts.sort(key=lambda record: record.created_at)
    if not drafts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='no pending methodology drafts remain')
    if len(iterations) >= campaign.max_iterations:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='campaign has reached max_iterations')
    return drafts[0]


def _load_metrics_payload(settings: Settings, run_id: str) -> dict[str, Any]:
    path = artifact_run_dir(settings, run_id) / 'metrics.json'
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_primary_metric(metrics: dict[str, Any]) -> tuple[str | None, float | None]:
    preferred = ['accuracy', 'f1', 'roc_auc', 'precision', 'recall']
    for key in preferred:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return key, float(value)
    numeric_items = [(key, float(value)) for key, value in metrics.items() if isinstance(value, (int, float))]
    if not numeric_items:
        return (None, None)
    numeric_items.sort(key=lambda item: item[0])
    return numeric_items[0]


def summarize_iteration_run(
    record: RunRecord,
    *,
    settings: Settings,
    submitter: JobSubmitter,
) -> dict[str, Any]:
    resolved = resolve_run_status(record, settings, submitter)
    metrics = _load_metrics_payload(settings, record.run_id)
    metric_name, metric_value = _extract_primary_metric(metrics)
    summary: dict[str, Any] = {
        'run_status': resolved.status,
        'run_detail': resolved.detail,
        'primary_metric_name': metric_name,
        'primary_metric_value': metric_value,
    }
    if metrics:
        summary['metrics'] = metrics
    return summary


def build_iteration_comparison(
    child_summary: dict[str, Any],
    parent_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison: dict[str, Any] = {
        'baseline_available': parent_summary is not None,
        'metric_name': child_summary.get('primary_metric_name'),
    }
    if parent_summary is None:
        comparison['detail'] = 'no prior scored baseline is available'
        return comparison
    if child_summary.get('primary_metric_name') != parent_summary.get('primary_metric_name'):
        comparison['detail'] = 'metric mismatch prevents automatic comparison'
        return comparison
    child_value = child_summary.get('primary_metric_value')
    parent_value = parent_summary.get('primary_metric_value')
    if not isinstance(child_value, (int, float)) or not isinstance(parent_value, (int, float)):
        comparison['detail'] = 'numeric metrics unavailable for automatic comparison'
        return comparison
    comparison['baseline_value'] = parent_value
    comparison['candidate_value'] = child_value
    comparison['delta'] = round(float(child_value) - float(parent_value), 6)
    comparison['detail'] = 'numeric comparison computed'
    return comparison


def build_decision(
    iteration: AutoresearchIterationRecord,
    child_summary: dict[str, Any],
    comparison_summary: dict[str, Any],
) -> tuple[str, str]:
    run_status = str(child_summary.get('run_status', 'unknown'))
    if run_status in {'failed', 'rejected'}:
        return ('discard', f'Run ended in terminal failure state: {run_status}.')
    delta = comparison_summary.get('delta')
    metric_name = comparison_summary.get('metric_name')
    if isinstance(delta, (int, float)) and metric_name:
        if delta > 0.01:
            return ('keep', f'Candidate improved {metric_name} by {delta:.4f} over the baseline.')
        if delta < -0.01:
            return ('discard', f'Candidate regressed {metric_name} by {abs(delta):.4f} relative to the baseline.')
        return ('escalate_for_review', f'Candidate changed {metric_name} by {delta:.4f}; review is required.')
    if run_status == 'succeeded' and isinstance(child_summary.get('primary_metric_value'), (int, float)):
        return ('keep', 'Candidate produced a successful bounded run with scored metrics, but no trusted baseline was available.')
    return ('escalate_for_review', 'Insufficient evidence for an automatic keep/discard decision.')


def summarize_campaign(
    store: RunStore,
    campaign: AutoresearchCampaignRecord,
) -> AutoresearchCampaignSummaryResponse:
    drafts = store.list_methodology_drafts(campaign.campaign_id)
    iterations = store.list_autoresearch_iterations(campaign.campaign_id)
    decisions = store.list_autoresearch_decisions(campaign.campaign_id)
    best_draft = store.get_methodology_draft(campaign.current_best_methodology_draft_id or '')
    latest_run = None
    if campaign.latest_iteration_id:
        latest_iteration = store.get_autoresearch_iteration(campaign.latest_iteration_id)
        if latest_iteration is not None:
            latest_run = store.get_run(latest_iteration.run_id)
    proposed_next_variants: list[str] = []
    if best_draft is not None:
        if len(best_draft.candidate_models) == 1:
            proposed_next_variants.append('Compare the current kept model against the next approved baseline.')
        proposed_next_variants.append('Run a metric-emphasis variant focused on the primary evaluation target.')
        proposed_next_variants.append('Run a bounded baseline-inclusion ablation on the same approved dataset split.')
    return AutoresearchCampaignSummaryResponse(
        campaign=campaign,
        methodology_drafts=drafts,
        iterations=iterations,
        decisions=decisions,
        best_methodology_draft=best_draft,
        latest_run=latest_run,
        proposed_next_variants=proposed_next_variants,
    )


def markdown_cell(lines: list[str]) -> dict[str, Any]:
    return {
        'cell_type': 'markdown',
        'metadata': {},
        'source': [line + '\n' for line in lines],
    }


def code_cell(lines: list[str]) -> dict[str, Any]:
    return {
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [],
        'source': [line + '\n' for line in lines],
    }


def build_autoresearch_notebook(
    campaign: AutoresearchCampaignRecord,
    methodology: MethodologyDraftRecord,
    workflow: WorkflowRegistryEntry | None = None,
) -> dict[str, Any]:
    runtime_requirements = workflow.runtime_requirements if workflow is not None else {}
    required_python_packages = runtime_requirements.get('required_python_packages', [])
    training_stack = runtime_requirements.get('training_stack', [])
    cells: list[dict[str, Any]] = [
        markdown_cell(
            [
                f'# Glasslab Autoresearch Campaign {campaign.campaign_id[:8]}',
                '',
                f'- objective: `{campaign.objective}`',
                f'- workflow: `{methodology.workflow_id}`',
                f'- methodology draft: `{methodology.methodology_draft_id}`',
                f'- method family: `{methodology.method_family}`',
            ]
        ),
        markdown_cell(
            [
                '## Hypothesis',
                '',
                methodology.hypothesis,
            ]
        ),
        markdown_cell(
            [
                '## Structured methodology',
                '',
                f'- datasets: `{", ".join(methodology.datasets) or "unknown"}`',
                f'- architectures: `{", ".join(methodology.architectures) or "unknown"}`',
                f'- baselines: `{", ".join(methodology.baselines) or "unknown"}`',
                f'- metrics: `{", ".join(methodology.metrics) or "unknown"}`',
                f'- resource profile: `{methodology.resource_profile}`',
                f'- bounded experimentability: `{methodology.bounded_experimentability}`',
                f'- preferred Python packages: `{", ".join(required_python_packages) or "unspecified"}`',
                f'- training stack: `{", ".join(training_stack) or "unspecified"}`',
            ]
        ),
        code_cell(
            [
                'import json',
                'from pprint import pprint',
                '',
                'methodology_draft = ' + json.dumps(methodology.model_dump(mode='json'), indent=2),
                '',
                'pprint(methodology_draft)',
            ]
        ),
        markdown_cell(
            [
                '## Mutation diff',
                '',
                'This notebook is a reviewable scaffold derived from the bounded methodology draft. It is not an executable authority by itself.',
            ]
        ),
        code_cell(
            [
                'mutation_diff = ' + json.dumps(methodology.mutation_diff, indent=2),
                'mutation_diff',
            ]
        ),
        markdown_cell(
            [
                '## Next checks',
                '',
                '- confirm the approved workflow inputs are still correct',
                '- confirm the required Python packages are available in the chosen runner image',
                '- confirm GPU scheduling only when the preferred workflow and resource profile require it',
                '- confirm the selected model family fits the bounded template',
                '- confirm the metric emphasis matches the research objective',
                '- only then launch the bounded validation run',
            ]
        ),
    ]
    return {
        'cells': cells,
        'metadata': {
            'kernelspec': {
                'display_name': 'Python 3',
                'language': 'python',
                'name': 'python3',
            },
            'language_info': {
                'name': 'python',
                'version': '3.11',
            },
            'glasslab': {
                'campaign_id': campaign.campaign_id,
                'methodology_draft_id': methodology.methodology_draft_id,
                'workflow_id': methodology.workflow_id,
                'kind': 'autoresearch-notebook-draft',
            },
        },
        'nbformat': 4,
        'nbformat_minor': 5,
    }


def write_autoresearch_notebook_draft(
    settings: Settings,
    campaign: AutoresearchCampaignRecord,
    methodology: MethodologyDraftRecord,
    workflow: WorkflowRegistryEntry | None = None,
    *,
    notebook: dict[str, Any] | None = None,
    filename: str = 'analysis_notebook.ipynb',
) -> tuple[str, dict[str, Any]]:
    notebook = notebook or build_autoresearch_notebook(campaign, methodology, workflow=workflow)
    target_dir = Path(settings.artifacts_mount_path) / 'workflow-api' / 'notebook-drafts' / campaign.campaign_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_text(json.dumps(notebook, indent=2), encoding='utf-8')
    return (path.as_uri(), notebook)


def build_coding_notebook_refinement_payload(
    campaign: AutoresearchCampaignRecord,
    methodology: MethodologyDraftRecord,
    workflow: WorkflowRegistryEntry | None,
    notebook: dict[str, Any],
    settings: Settings,
    *,
    design: DesignDraftRecord | None = None,
    interpretation: InterpretationRecord | None = None,
) -> dict[str, Any]:
    runtime_requirements = workflow.runtime_requirements if workflow is not None else {}
    return {
        'model': settings.coding_notebook_model,
        'stream': False,
        'format': 'json',
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You refine Glasslab Jupyter notebooks for bounded, reviewable methodology validation. '
                    'Do not change the research objective, do not introduce unrestricted shell/code mutation, '
                    'and do not invent execution manifests. '
                    'Return only valid JSON with top-level keys "notebook" and optional "warnings".'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps(
                    {
                        'request_id': methodology.methodology_draft_id,
                        'campaign': campaign.model_dump(mode='json'),
                        'methodology_draft': methodology.model_dump(mode='json'),
                        'workflow': workflow.model_dump(mode='json') if workflow is not None else None,
                        'design_draft': design.model_dump(mode='json') if design is not None else None,
                        'interpretation': interpretation.model_dump(mode='json') if interpretation is not None else None,
                        'runtime_requirements': runtime_requirements,
                        'notebook': notebook,
                        'instructions': [
                            'Refine this Glasslab notebook without changing its bounded research objective.',
                            'Keep the notebook reviewable and tied to the approved workflow template.',
                            'Add concrete but bounded cells for dataset loading, package requirements, metrics, experiment checks, and result interpretation where helpful.',
                            'Prefer one additional code cell for dataset or artifact loading and one additional markdown cell for runtime or evaluation checks.',
                            'Only mention Python packages that are already required by or clearly compatible with the workflow runtime requirements.',
                            'Preserve nbformat metadata and return the full notebook object.',
                        ],
                    },
                    indent=2,
                ),
            },
        ],
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError('coding notebook model returned empty content')
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError('coding notebook model response did not contain a JSON object')
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError('coding notebook model response JSON was not an object')
    return payload


def _validate_notebook_payload(notebook: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(notebook, dict):
        raise ValueError('coding notebook model response missing notebook object')
    if not isinstance(notebook.get('cells'), list):
        raise ValueError('refined notebook is missing cells list')
    if notebook.get('nbformat') != 4:
        notebook['nbformat'] = 4
    notebook.setdefault('nbformat_minor', 5)
    metadata = notebook.get('metadata')
    if not isinstance(metadata, dict):
        notebook['metadata'] = {}
    return notebook


def _extract_imported_python_packages(notebook: dict[str, Any]) -> list[str]:
    packages: list[str] = []
    for cell in notebook.get('cells', []):
        if not isinstance(cell, dict) or cell.get('cell_type') != 'code':
            continue
        source = ''.join(cell.get('source', []))
        for raw_line in source.splitlines():
            line = raw_line.strip()
            if line.startswith('import '):
                targets = line.removeprefix('import ').split(',')
                for target in targets:
                    package = target.strip().split(' as ')[0].split('.')[0].strip()
                    if package:
                        packages.append(package)
            elif line.startswith('from '):
                package = line.removeprefix('from ').split(' import ')[0].split('.')[0].strip()
                if package:
                    packages.append(package)
    return _dedupe(packages)


def _validate_notebook_runtime_contract(
    notebook: dict[str, Any],
    workflow: WorkflowRegistryEntry | None,
) -> list[str]:
    if workflow is None:
        return []
    runtime_requirements = workflow.runtime_requirements or {}
    allowed_packages = _dedupe([str(item) for item in runtime_requirements.get('required_python_packages', [])])
    if not allowed_packages:
        return []
    imported_packages = _extract_imported_python_packages(notebook)
    extras = [package for package in imported_packages if package not in allowed_packages and package not in {'json', 'pathlib', 'pprint'}]
    if not extras:
        return []
    return [
        'refined notebook imports packages outside the approved workflow runtime: '
        + ', '.join(extras)
        + '; review before execution'
    ]


def call_coding_notebook_agent(
    campaign: AutoresearchCampaignRecord,
    methodology: MethodologyDraftRecord,
    workflow: WorkflowRegistryEntry | None,
    notebook: dict[str, Any],
    settings: Settings,
    *,
    design: DesignDraftRecord | None = None,
    interpretation: InterpretationRecord | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not settings.coding_notebook_agent_enabled:
        return None, ['coding notebook agent is disabled; using deterministic notebook scaffold']

    payload = build_coding_notebook_refinement_payload(
        campaign,
        methodology,
        workflow,
        notebook,
        settings,
        design=design,
        interpretation=interpretation,
    )
    request_obj = urllib_request.Request(
        settings.coding_notebook_agent_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib_request.urlopen(request_obj, timeout=settings.coding_notebook_agent_timeout_seconds) as response:
            body = json.loads(response.read().decode('utf-8'))
        content = (
            body.get('message', {}).get('content')
            if isinstance(body.get('message'), dict)
            else None
        )
        if not isinstance(content, str):
            raise ValueError('coding notebook model response missing message.content')
        parsed = _extract_json_object(content)
        refined = _validate_notebook_payload(parsed.get('notebook'))
        warnings = [str(item) for item in parsed.get('warnings', []) if isinstance(item, str)]
        warnings.extend(_validate_notebook_runtime_contract(refined, workflow))
        return refined, warnings
    except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return None, [f'coding notebook agent fallback: {exc}']


def build_campaign_and_seed(
    store: RunStore,
    registry: WorkflowRegistry,
    request: AutoresearchCampaignCreateRequest,
) -> tuple[AutoresearchCampaignRecord, MethodologyDraftRecord]:
    session_id = request.session_id
    if session_id is None:
        session = store.get_latest_research_session()
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='no research session has been created yet')
        session_id = session.session_id
    design = _find_latest_design_for_campaign(store, session_id=session_id, source_design_id=request.source_design_id)
    workflow = registry.get_workflow(design.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow registry entry not found')
    if workflow.execution_status != 'ready':
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='workflow is not approved for autoresearch execution')
    objective = request.objective or design.objective
    campaign = build_autoresearch_campaign(
        request,
        session_id=session_id,
        source_design_id=design.design_id,
        objective=objective,
    )
    seed = build_seed_methodology_draft(campaign, design, workflow)
    campaign = campaign.model_copy(
        update={
            'seed_methodology_draft_ids': [seed.methodology_draft_id],
            'current_best_methodology_draft_id': seed.methodology_draft_id,
        }
    )
    store.save_autoresearch_campaign(campaign)
    store.save_methodology_draft(seed)
    touch_research_session(
        store,
        session_id,
        latest_methodology_draft_id=seed.methodology_draft_id,
        latest_autoresearch_campaign_id=campaign.campaign_id,
        decision_log=[f'autoresearch campaign created: {campaign.campaign_id}'],
    )
    return (campaign, seed)
