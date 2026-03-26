from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.run_artifacts import (
    artifact_run_dir,
    build_artifacts_from_directory,
    load_artifacts_from_disk,
    load_logs_from_disk,
    load_status_from_disk,
    parse_log_line,
    resolve_run_status,
)
from app.schemas import JobSubmissionReceipt, RunRecord
from services.common.schemas import RunManifest, RunStatus


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        registry_dir=str(tmp_path),
        artifacts_mount_path=str(tmp_path / 'artifacts'),
    )


def build_run_record(run_id: str, status: RunStatus) -> RunRecord:
    now = datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc)
    manifest = RunManifest(
        run_id=run_id,
        workflow_id='generic-tabular-benchmark',
        workflow_family='tabular-benchmark',
        display_name='Tabular Benchmark',
        objective='Test artifact helpers.',
        submitted_by='tester',
        submitted_at=now,
        run_priority='user',
        inputs={'dataset_name': 'titanic'},
        requested_models=['logistic_regression'],
        resource_profile='cpu-small',
        resource_requests={},
        resource_limits={},
        node_selector={},
        runner_image='busybox:latest',
        evaluator_type='none',
        approval_tier='tier-1-read-only',
        expected_artifacts={'required': ['status.json'], 'optional': ['logs/runner.log']},
    )
    return RunRecord(
        run_id=run_id,
        workflow_id='generic-tabular-benchmark',
        created_at=now,
        updated_at=now,
        manifest=manifest,
        status=status,
        job_submission=JobSubmissionReceipt(
            job_name='job',
            namespace='default',
            accepted_at=now,
            status='accepted',
            detail='ok',
        ),
    )


def test_load_status_artifacts_and_logs_from_disk(tmp_path) -> None:
    settings = build_settings(tmp_path)
    run_id = 'run-123'
    run_dir = artifact_run_dir(settings, run_id)
    (run_dir / 'logs').mkdir(parents=True)
    (run_dir / 'status.json').write_text(
        '{"run_id":"run-123","status":"succeeded","updated_at":"2026-03-26T12:00:00Z","detail":"done"}'
    )
    (run_dir / 'artifacts_index.json').write_text(
        '{"run_id":"run-123","artifacts":[{"name":"status.json","path":"artifacts/run-123/status.json","media_type":"application/json","required":true}]}'
    )
    (run_dir / 'logs' / 'runner.log').write_text(
        '2026-03-26 12:00:00,123 INFO glasslab.runner completed run\n'
    )

    status = load_status_from_disk(settings, run_id)
    assert status is not None
    assert status.status == 'succeeded'

    artifacts = load_artifacts_from_disk(settings, run_id)
    assert artifacts is not None
    assert artifacts.artifacts[0].name == 'status.json'

    fallback_artifacts = build_artifacts_from_directory(settings, run_id)
    assert fallback_artifacts is not None
    assert any(entry.name == 'logs/' for entry in fallback_artifacts.artifacts)
    assert any(entry.name == 'logs/runner.log' for entry in fallback_artifacts.artifacts)

    logs = load_logs_from_disk(settings, run_id)
    assert len(logs) == 1
    assert logs[0].message == 'completed run'
    assert logs[0].payload == {'logger': 'glasslab.runner'}


def test_parse_log_line_and_resolve_run_status_prefers_disk(tmp_path) -> None:
    settings = build_settings(tmp_path)
    run_id = 'run-456'
    run_dir = artifact_run_dir(settings, run_id)
    run_dir.mkdir(parents=True)
    (run_dir / 'status.json').write_text(
        '{"run_id":"run-456","status":"succeeded","updated_at":"2026-03-26T12:00:00Z","detail":"done"}'
    )

    parsed = parse_log_line('2026-03-26 12:00:00,123 INFO glasslab.runner completed run')
    assert parsed.level == 'INFO'
    assert parsed.message == 'completed run'

    class FakeSubmitter:
        def get_live_status(self, record):
            return RunStatus(
                run_id=record.run_id,
                status='running',
                updated_at=datetime(2026, 3, 26, 12, 1, tzinfo=timezone.utc),
                detail='live',
            )

    record = build_run_record(
        run_id,
        RunStatus(
            run_id=run_id,
            status='queued',
            updated_at=datetime(2026, 3, 26, 11, 59, tzinfo=timezone.utc),
            detail='queued',
        ),
    )
    resolved = resolve_run_status(record, settings, FakeSubmitter())
    assert resolved.status == 'succeeded'
