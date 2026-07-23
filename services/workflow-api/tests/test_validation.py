import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

for module_name in list(sys.modules):
    if module_name == 'app' or module_name.startswith('app.'):
        del sys.modules[module_name]

from app.registry import WorkflowRegistry
from app.investigation_routes import evaluator_contract_issues
from app.job_submission import (
    _active_deadline_seconds,
    _asset_volume_subpath,
    _research_workspace_asset_locations,
    _research_workspace_volume_mount_specs,
)
from app.schemas import InvestigationPlanCreateRequest, RunCreateRequest
from app.validation import validate_run_request
from services.common.schemas import RunManifest

REPO_ROOT = Path(__file__).resolve().parents[3]


def build_workspace_execution(
    execution_id: str,
    *,
    depends_on: list[str] | None = None,
) -> dict[str, object]:
    return {
        'execution_id': execution_id,
        'objective': f'Execute the frozen {execution_id} workspace.',
        'experiment_type': 'research-workspace-job',
        'workload_id': 'research-workspace-cpu-v1',
        'data_access_scope': 'solve',
        'depends_on': depends_on or [],
        'workspace': {
            'task_bundle': {
                'uri': 's3://datasets/task.zip',
                'sha256': 'a' * 64,
            },
            'source_bundle': {
                'uri': 's3://artifacts/submissions/source.zip',
                'sha256': 'b' * 64,
            },
            'command': ['python3', 'run.py'],
        },
        'budget': {
            'budget_mode': 'wallclock',
            'max_wallclock_minutes': 5,
        },
        'artifact_contract': {'required': ['status.json']},
        'evaluator_contract': {'evaluator_type': 'rubric-gated-v1'},
    }


def test_validation_rejects_missing_inputs_and_bad_resource_profile() -> None:
    registry = WorkflowRegistry(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions')
    workflow = registry.get_workflow('generic-tabular-benchmark')
    assert workflow is not None

    request = RunCreateRequest(
        workflow_id='generic-tabular-benchmark',
        objective='Benchmark approved models on Titanic.',
        inputs={
            'dataset_name': 'titanic',
            'train_uri': 's3://datasets/titanic/train.csv',
        },
        models=['logistic_regression'],
        resource_profile='gpu-small',
    )

    issues = validate_run_request(request, workflow)
    fields = {issue.field for issue in issues}
    assert 'inputs.test_uri' in fields
    assert 'inputs.target_column' in fields
    assert 'resource_profile' in fields


def test_validation_rejects_disallowed_models() -> None:
    registry = WorkflowRegistry(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions')
    workflow = registry.get_workflow('generic-tabular-benchmark')
    assert workflow is not None

    request = RunCreateRequest(
        workflow_id='generic-tabular-benchmark',
        objective='Benchmark approved models on Titanic.',
        inputs={
            'dataset_name': 'titanic',
            'train_uri': 's3://datasets/titanic/train.csv',
            'test_uri': 's3://datasets/titanic/test.csv',
            'target_column': 'Survived',
        },
        models=['made_up_model'],
    )

    issues = validate_run_request(request, workflow)
    assert len(issues) == 1
    assert issues[0].field == 'models'
    assert 'made_up_model' in issues[0].message


def test_validation_accepts_gpu_neural_net_workflow_request() -> None:
    registry = WorkflowRegistry(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions')
    workflow = registry.get_workflow('gpu-experiment')
    assert workflow is not None

    request = RunCreateRequest(
        workflow_id='gpu-experiment',
        objective='Train a bounded neural-net experiment on the approved GPU worker.',
        inputs={
            'dataset_uri': 's3://datasets/neural-net/train',
            'model_family': 'pytorch-template-v1',
            'training_notes': 'Use a single GPU, bounded epochs, and report validation loss.',
        },
        models=['pytorch-template-v1'],
        resource_profile='gpu-small',
    )

    issues = validate_run_request(request, workflow)
    assert issues == []


def test_generic_run_wallclock_budget_becomes_kubernetes_deadline() -> None:
    manifest = RunManifest(
        run_id='run-1',
        workflow_id='research-workspace-cpu-v1',
        workflow_family='research-workspace',
        display_name='Research Workspace CPU v1',
        objective='Execute one frozen research workspace.',
        submitted_by='test-suite',
        submitted_at=datetime.now(timezone.utc),
        inputs={},
        requested_models=['agent-generated-python'],
        resource_profile='cpu-research-medium',
        runner_image='ghcr.io/example/research-workspace:0.1.0',
        evaluator_type='rubric-gated-v1',
        approval_tier='tier-2-approved-execution',
        expected_artifacts={'required': ['status.json'], 'optional': []},
        experiment_type='research-workspace-job',
        workload_id='research-workspace-cpu-v1',
        entrypoint=['python3', '-m', 'runner'],
        budget={'max_wallclock_minutes': 17},
    )

    assert _active_deadline_seconds(manifest) == 17 * 60


def test_investigation_plan_accepts_acyclic_execution_graph() -> None:
    plan = InvestigationPlanCreateRequest(
        title='Two-stage frozen plan',
        rationale='Pre-register training and evaluation as one approved graph.',
        hypothesis_ids=['hypothesis-1'],
        executions=[
            build_workspace_execution('train'),
            build_workspace_execution('evaluate', depends_on=['train']),
        ],
    )

    assert [execution.execution_id for execution in plan.executions] == [
        'train',
        'evaluate',
    ]


@pytest.mark.parametrize(
    'executions, expected_message',
    [
        (
            [
                build_workspace_execution('train', depends_on=['evaluate']),
                build_workspace_execution('evaluate', depends_on=['train']),
            ],
            'acyclic graph',
        ),
        (
            [build_workspace_execution('evaluate', depends_on=['missing'])],
            'unknown dependencies',
        ),
    ],
)
def test_investigation_plan_rejects_invalid_execution_graph(
    executions: list[dict[str, object]],
    expected_message: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        InvestigationPlanCreateRequest(
            title='Invalid execution graph',
            rationale='This plan must be rejected before it can be approved.',
            hypothesis_ids=['hypothesis-1'],
            executions=executions,
        )


def test_research_workspace_mounts_only_declared_asset_subpaths() -> None:
    manifest = RunManifest(
        run_id='run-isolated',
        workflow_id='research-workspace-cpu-v1',
        workflow_family='research-workspace',
        display_name='Research Workspace CPU v1',
        objective='Execute one isolated research workspace.',
        submitted_by='test-suite',
        submitted_at=datetime.now(timezone.utc),
        inputs={},
        requested_models=['agent-generated-python'],
        resource_profile='cpu-research-medium',
        runner_image='ghcr.io/example/research-workspace:0.1.0',
        evaluator_type='rubric-gated-v1',
        approval_tier='tier-2-approved-execution',
        expected_artifacts={'required': ['status.json'], 'optional': []},
        experiment_type='research-workspace-job',
        workload_id='research-workspace-cpu-v1',
        schema_ref='glasslab-investigation-workspace-v1',
        entrypoint=['python3', '-m', 'runner'],
        config_payload={
            'workspace': {
                'task_bundle': {
                    'uri': 's3://datasets/benchmarks/adult/task.zip',
                },
                'source_bundle': {
                    'uri': 's3://artifacts/submissions/adult/source.zip',
                },
            },
            'dataset_contracts': [
                {
                    'name': 'adult_train',
                    'asset': {
                        'uri': 's3://datasets/uci-adult/adult.data',
                    },
                }
            ],
        },
        budget={'max_wallclock_minutes': 5},
    )

    assert _research_workspace_asset_locations(manifest) == [
        ('dataset-volume', 'benchmarks/adult/task.zip'),
        ('artifacts-volume', 'submissions/adult/source.zip'),
        ('dataset-volume', 'uci-adult/adult.data'),
    ]
    settings = type(
        'MountSettings',
        (),
        {
            'dataset_mount_path': '/mnt/datasets',
            'artifacts_mount_path': '/mnt/artifacts',
        },
    )()
    assert _research_workspace_volume_mount_specs(manifest, settings) == [
        {
            'name': 'dataset-volume',
            'mount_path': '/mnt/datasets/benchmarks/adult/task.zip',
            'sub_path': 'benchmarks/adult/task.zip',
            'read_only': True,
        },
        {
            'name': 'artifacts-volume',
            'mount_path': '/mnt/artifacts/submissions/adult/source.zip',
            'sub_path': 'submissions/adult/source.zip',
            'read_only': True,
        },
        {
            'name': 'dataset-volume',
            'mount_path': '/mnt/datasets/uci-adult/adult.data',
            'sub_path': 'uci-adult/adult.data',
            'read_only': True,
        },
        {
            'name': 'artifacts-volume',
            'mount_path': '/mnt/artifacts/run-isolated',
            'sub_path': 'run-isolated',
            'read_only': False,
        },
    ]


@pytest.mark.parametrize(
    'uri',
    [
        'file:///mnt/datasets/secret.csv',
        'https://example.com/source.zip',
        's3://datasets/../hidden.csv',
        's3://artifacts/../other-run/source.zip',
    ],
)
def test_research_workspace_rejects_unapproved_mount_uri(uri: str) -> None:
    with pytest.raises(ValueError):
        _asset_volume_subpath(uri)


def test_claim_evaluator_contract_requires_primary_metric_and_guardrails() -> None:
    execution_payload = build_workspace_execution('evaluate')
    execution_payload['evaluator_contract'] = {
        'evaluator_type': 'rubric-gated-v1',
        'primary_metric': {
            'name': 'rubric_score',
            'direction': 'maximize',
        },
        'guardrails': [
            {
                'name': 'integrity_pass',
                'minimum': 1,
                'required': True,
            }
        ],
    }
    plan = InvestigationPlanCreateRequest(
        title='Evaluator contract plan',
        rationale='Require an integrity gate before storing scientific claims.',
        hypothesis_ids=['hypothesis-1'],
        executions=[execution_payload],
    )
    execution = plan.executions[0]

    assert evaluator_contract_issues(
        {'rubric_score': 88, 'integrity_pass': 1},
        execution,
    ) == []
    assert evaluator_contract_issues(
        {'rubric_score': 88, 'integrity_pass': 0},
        execution,
    ) == ['guardrail integrity_pass is below minimum 1.0']
    assert evaluator_contract_issues({}, execution) == [
        'primary metric is missing or non-numeric: rubric_score',
        'required guardrail metric is missing: integrity_pass',
    ]
