from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from io import BytesIO

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


def _minio_client(settings: Settings):
    try:
        from minio import Minio
    except ImportError as exc:
        raise RuntimeError('minio package is required for MinIO support') from exc
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def _is_minio_path(path: str) -> bool:
    parsed = urlparse(path)
    return parsed.scheme == 's3'


def artifact_run_dir(settings: Settings, run_id: str) -> Path:
    if _is_minio_path(settings.artifacts_mount_path):
        return f"s3://{settings.artifacts_mount_path.removeprefix('s3://')}/{run_id}"
    return Path(settings.artifacts_mount_path) / run_id


def _read_file(path: str | Path) -> str:
    if isinstance(path, str) and _is_minio_path(path):
        parsed = urlparse(path)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        client = _minio_client(Settings())
        obj = client.get_object(bucket, key)
        try:
            return obj.read().decode('utf-8')
        finally:
            obj.close()
            obj.release_ram()
    else:
        return Path(path).read_text()


def _list_dir(path: str | Path) -> list[tuple[str, bool]]:
    if isinstance(path, str) and _is_minio_path(path):
        parsed = urlparse(path)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip('/')
        client = _minio_client(Settings())
        objects = []
        for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
            rel = obj.object_name[len(prefix):].lstrip('/')
            if rel:
                is_dir = obj.object_name.endswith('/') or (not obj.object_name.count('/') == (prefix.count('/') if prefix else 0))
                objects.append((rel, is_dir))
        return objects
    else:
        root = Path(path)
        return [(p.name, p.is_dir()) for p in root.iterdir()]


def _file_exists(path: str | Path) -> bool:
    if isinstance(path, str) and _is_minio_path(path):
        parsed = urlparse(path)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        client = _minio_client(Settings())
        try:
            client.stat_object(bucket, key)
            return True
        except Exception:
            return False
    else:
        return Path(path).exists()


def _get_file_size(path: str | Path) -> int:
    if isinstance(path, str) and _is_minio_path(path):
        parsed = urlparse(path)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        client = _minio_client(Settings())
        return client.stat_object(bucket, key).size
    else:
        return Path(path).stat().st_size


def load_status_from_disk(settings: Settings, run_id: str) -> RunStatus | None:
    path = artifact_run_dir(settings, run_id) / 'status.json'
    if not _file_exists(path):
        return None
    payload = json.loads(_read_file(path))
    return RunStatus.model_validate(payload)

def build_artifacts_from_directory(settings: Settings, run_id: str) -> ArtifactsIndex | None:
    root = artifact_run_dir(settings, run_id)
    if not _file_exists(root):
        return None
    artifacts: list[ArtifactIndexEntry] = []
    entries = _list_dir(root)
    for name, is_dir in sorted(entries):
        relative = name
        if is_dir:
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
                media_type=MEDIA_TYPES.get(Path(relative).suffix.lower(), 'application/octet-stream'),
                required=relative in {'run_manifest.json', 'config.json', 'metrics.json', 'artifacts_index.json', 'report.md', 'status.json', 'logs/runner.log'},
                size_bytes=_get_file_size(f"{root}/{relative}"),
                description='Discovered from shared artifacts volume',
            )
        )
    return ArtifactsIndex(run_id=run_id, artifacts=artifacts)


def load_artifacts_from_disk(settings: Settings, run_id: str) -> ArtifactsIndex | None:
    root = artifact_run_dir(settings, run_id)
    index_path = f"{root}/artifacts_index.json" if isinstance(root, str) else root / 'artifacts_index.json'
    if _file_exists(index_path):
        payload = json.loads(_read_file(index_path))
        return ArtifactsIndex.model_validate(payload)
    return build_artifacts_from_directory(settings, run_id)


def parse_log_line(line: str) -> LogEntry:
    match = LOG_LINE_RE.match(line)
    if not match:
        return LogEntry(timestamp=datetime.now(timezone.utc), level='INFO', message=line)
    timestamp = datetime.strptime(match.group('ts'), '%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=timezone.utc)
    return LogEntry(timestamp=timestamp, level=match.group('level'), message=match.group('message'), payload={'logger': match.group('logger')})


def load_logs_from_disk(settings: Settings, run_id: str) -> list[LogEntry]:
    root = artifact_run_dir(settings, run_id)
    log_path = f"{root}/logs/runner.log" if isinstance(root, str) else root / 'logs' / 'runner.log'
    if not _file_exists(log_path):
        return []
    return [parse_log_line(line) for line in _read_file(log_path).splitlines() if line.strip()]


def resolve_run_status(record: RunRecord, settings: Settings, submitter: JobSubmitter) -> RunStatus:
    disk_status = load_status_from_disk(settings, record.run_id)
    if disk_status is not None:
        return disk_status
    live_status = submitter.get_live_status(record)
    if live_status is not None:
        return live_status
    return record.status
