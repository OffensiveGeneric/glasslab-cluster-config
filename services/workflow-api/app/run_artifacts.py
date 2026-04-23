from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path

from services.common.schemas import ArtifactIndexEntry, ArtifactsIndex, RunStatus

from .config import Settings
from .job_submission import JobSubmitter
from .schemas import LogEntry, RunRecord

MEDIA_TYPES = {
    '.json': 'application/json',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.txt': 'text/plain',
    '.log': 'text/plain',
}

LOG_LINE_RE = re.compile(r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<level>[A-Z]+) (?P<logger>[^ ]+) (?P<message>.*)$')


def artifact_run_dir(settings: Settings, run_id: str) -> Path:
    return Path(settings.artifacts_mount_path) / run_id


def load_status_from_disk(settings: Settings, run_id: str) -> RunStatus | None:
    path = artifact_run_dir(settings, run_id) / 'status.json'
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    payload.setdefault('run_id', run_id)
    payload.setdefault('updated_at', datetime.now(timezone.utc).isoformat())
    try:
        return RunStatus.model_validate(payload)
    except Exception:
        return None


def build_artifacts_from_directory(settings: Settings, run_id: str) -> ArtifactsIndex | None:
    root = artifact_run_dir(settings, run_id)
    if not root.exists():
        return None
    artifacts: list[ArtifactIndexEntry] = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            artifacts.append(
                ArtifactIndexEntry(
                    name=f'{relative}/',
                    path=f'artifacts/{run_id}/{relative}/',
                    media_type='inode/directory',
                    required=relative == 'logs',
                    description='Discovered from shared artifacts volume',
                )
            )
            continue
        artifacts.append(
            ArtifactIndexEntry(
                name=relative,
                path=f'artifacts/{run_id}/{relative}',
                media_type=MEDIA_TYPES.get(path.suffix.lower(), 'application/octet-stream'),
                required=relative in {'run_manifest.json', 'config.json', 'metrics.json', 'artifacts_index.json', 'report.md', 'status.json', 'logs/runner.log'},
                size_bytes=path.stat().st_size,
                description='Discovered from shared artifacts volume',
            )
        )
    return ArtifactsIndex(run_id=run_id, artifacts=artifacts)


def load_artifacts_from_disk(settings: Settings, run_id: str) -> ArtifactsIndex | None:
    index_path = artifact_run_dir(settings, run_id) / 'artifacts_index.json'
    if index_path.exists():
        payload = json.loads(index_path.read_text())
        return ArtifactsIndex.model_validate(payload)
    return build_artifacts_from_directory(settings, run_id)


def parse_log_line(line: str) -> LogEntry:
    match = LOG_LINE_RE.match(line)
    if not match:
        return LogEntry(timestamp=datetime.now(timezone.utc), level='INFO', message=line)
    timestamp = datetime.strptime(match.group('ts'), '%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=timezone.utc)
    return LogEntry(timestamp=timestamp, level=match.group('level'), message=match.group('message'), payload={'logger': match.group('logger')})


def load_logs_from_disk(settings: Settings, run_id: str) -> list[LogEntry]:
    log_path = artifact_run_dir(settings, run_id) / 'logs' / 'runner.log'
    if not log_path.exists():
        return []
    return [parse_log_line(line) for line in log_path.read_text().splitlines() if line.strip()]


def resolve_run_status(record: RunRecord, settings: Settings, submitter: JobSubmitter) -> RunStatus:
    disk_status = load_status_from_disk(settings, record.run_id)
    if disk_status is not None:
        return disk_status
    live_status = submitter.get_live_status(record)
    if live_status is not None:
        return live_status
    return record.status
