import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

for module_name in list(sys.modules):
    if module_name == 'app' or module_name.startswith('app.'):
        del sys.modules[module_name]

from app.config import Settings
from app.persistence import JsonFileRunStore, create_run_store
from app.schemas import (
    OperationRecord,
    PaperIntakeQueueRecord,
    ResearchProblemRecord,
    ResearchSessionRecord,
    ScheduledExecutionRecord,
    SourceDocumentRecord,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_settings_fail_closed_when_memory_store_is_disallowed() -> None:
    with pytest.raises(ValueError, match='allow_inmemory_store=false'):
        Settings(
            registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
            store_backend='memory',
            allow_inmemory_store=False,
        )


def test_json_store_rejects_blank_path() -> None:
    with pytest.raises(ValueError, match='non-empty store_json_path'):
        Settings(
            registry_dir=str(REPO_ROOT / 'services' / 'workflow-registry' / 'definitions'),
            store_backend='json',
            store_json_path='   ',
        )


def test_json_store_persists_session_and_stage_metadata_across_restart(tmp_path: Path) -> None:
    state_path = tmp_path / 'run-store.json'
    now = datetime(2026, 3, 26, 15, 30, tzinfo=timezone.utc)

    store = JsonFileRunStore(state_path)

    session = ResearchSessionRecord(
        session_id='session-1',
        created_at=now,
        updated_at=now,
        status='active',
        title='Durable state validation',
        goal_statement='Keep the durable store path explicit before Postgres lands.',
        priorities=['durability'],
        submitted_by='glasslab-operator',
        latest_problem_id='problem-1',
        latest_queue_id='queue-1',
        latest_document_id='document-1',
    )
    problem = ResearchProblemRecord(
        problem_id='problem-1',
        created_at=now,
        updated_at=now,
        status='ready',
        problem_statement='Verify the JSON backend survives a restart.',
        submitted_by='glasslab-operator',
        session_id=session.session_id,
    )
    queue = PaperIntakeQueueRecord(
        queue_id='queue-1',
        created_at=now,
        updated_at=now,
        problem_statement='Verify the JSON backend survives a restart.',
        submitted_by='glasslab-operator',
        session_id=session.session_id,
    )
    document = SourceDocumentRecord(
        document_id='document-1',
        created_at=now,
        updated_at=now,
        status='fetched',
        source_url='https://example.org/paper.pdf',
        submitted_by='glasslab-operator',
        storage_uri='file:///tmp/paper.pdf',
        session_id=session.session_id,
    )
    execution = ScheduledExecutionRecord(
        execution_id='execution-1',
        schedule_id='schedule-1',
        operation_type='paper-intake',
        started_at=now,
        finished_at=now,
        result_status='ok',
        result_detail='persisted',
    )
    operation = OperationRecord(
        operation_id='operation-1',
        operation_type='paper-intake',
        status='completed',
        started_at=now,
        finished_at=now,
        session_id=session.session_id,
        queue_id=queue.queue_id,
        document_id=document.document_id,
        result_detail='stored session and stage metadata',
    )

    store.save_research_session(session)
    store.save_research_problem(problem)
    store.save_paper_intake_queue(queue)
    store.save_source_document(document)
    store.save_execution(execution)
    store.save_operation(operation)

    reloaded = create_run_store('json', state_path=state_path)

    reloaded_session = reloaded.get_latest_research_session()
    assert reloaded_session is not None
    assert reloaded_session.session_id == session.session_id
    assert reloaded_session.latest_queue_id == queue.queue_id
    assert reloaded.get_research_problem(problem.problem_id) == problem
    assert reloaded.get_paper_intake_queue(queue.queue_id) == queue
    assert reloaded.get_source_document(document.document_id) == document
    assert reloaded.get_latest_operation() == operation
    assert reloaded.list_executions(schedule_id='schedule-1') == [execution]
