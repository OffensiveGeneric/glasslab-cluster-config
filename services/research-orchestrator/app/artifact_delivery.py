from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import zipfile

from .schemas import ArtifactRecord, JobRecord, JobStatus


class ArtifactDeliveryError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactBundle:
    filename: str
    content: bytes
    artifact_count: int


class VerifiedArtifactReader:
    def __init__(self, shared_mount_root: str) -> None:
        self.root = Path(shared_mount_root).resolve()

    def resolve(self, artifact: ArtifactRecord) -> Path:
        metadata_path = artifact.metadata.get('path')
        candidates: list[Path] = []
        if isinstance(metadata_path, str) and metadata_path:
            candidates.append(Path(metadata_path))

        uri = artifact.uri
        if uri.startswith('artifact://'):
            relative = uri.removeprefix('artifact://')
            candidates.append(self.root / relative)
        elif not uri.startswith(('s3://', 'job://', 'contract://')):
            candidates.append(Path(uri) if uri.startswith('/') else self.root / uri)

        for candidate in candidates:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self.root):
                continue
            if resolved.is_symlink() or not resolved.is_file():
                continue
            digest = sha256()
            with resolved.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != artifact.sha256:
                raise ArtifactDeliveryError(
                    f'artifact digest mismatch: {artifact.uri}'
                )
            return resolved
        raise ArtifactDeliveryError(
            f'artifact content is unavailable: {artifact.uri}'
        )

    def read(self, artifact: ArtifactRecord, *, maximum_bytes: int) -> bytes:
        path = self.resolve(artifact)
        size = path.stat().st_size
        if size > maximum_bytes:
            raise ArtifactDeliveryError(
                f'artifact exceeds delivery limit: {artifact.uri}'
            )
        return path.read_bytes()


def _safe_archive_name(value: str) -> str:
    normalized = value.strip().replace('\\', '/').lstrip('/')
    path = PurePosixPath(normalized)
    if not normalized or '..' in path.parts or any(not part for part in path.parts):
        raise ArtifactDeliveryError(f'unsafe artifact archive path: {value}')
    return path.as_posix()


def _artifact_archive_name(artifact: ArtifactRecord) -> str:
    basename = Path(artifact.uri).name or Path(artifact.type).name
    if artifact.job_id:
        relative_type = _safe_archive_name(artifact.type)
        return f'jobs/{artifact.job_id}/{relative_type}'
    return f'run/{_safe_archive_name(artifact.type)}/{_safe_archive_name(basename)}'


def _latest_run_artifacts(
    artifacts: Iterable[ArtifactRecord],
) -> list[ArtifactRecord]:
    latest: dict[str, ArtifactRecord] = {}
    job_artifacts: list[ArtifactRecord] = []
    for artifact in artifacts:
        if artifact.job_id:
            job_artifacts.append(artifact)
        else:
            latest[artifact.type] = artifact
    return [*job_artifacts, *latest.values()]


def build_run_artifact_bundle(
    *,
    run_id: str,
    artifacts: list[ArtifactRecord],
    jobs: list[JobRecord],
    shared_mount_root: str,
    maximum_bytes: int,
    include_source: bool = False,
) -> ArtifactBundle:
    succeeded_job_ids = {
        job.job_id for job in jobs if job.status == JobStatus.SUCCEEDED
    }
    selected = [
        artifact
        for artifact in _latest_run_artifacts(artifacts)
        if artifact.job_id is None or artifact.job_id in succeeded_job_ids
    ]
    if not include_source:
        selected = [
            artifact
            for artifact in selected
            if Path(artifact.uri).name not in {'source.zip', 'task.zip'}
            and Path(artifact.type).name not in {'source.zip', 'task.zip'}
        ]

    reader = VerifiedArtifactReader(shared_mount_root)
    delivered: list[tuple[ArtifactRecord, str, bytes]] = []
    used_names: set[str] = set()
    total = 0
    unavailable: list[dict[str, str]] = []
    for artifact in selected:
        try:
            content = reader.read(artifact, maximum_bytes=maximum_bytes)
            archive_name = _artifact_archive_name(artifact)
            if archive_name in used_names:
                archive_name = (
                    f'{archive_name}.{artifact.sha256[:12]}'
                )
            total += len(content)
            if total > maximum_bytes:
                raise ArtifactDeliveryError(
                    'artifact bundle exceeds the Discord delivery limit; '
                    'retry without source bundles or use the artifact store'
                )
            used_names.add(archive_name)
            delivered.append((artifact, archive_name, content))
        except ArtifactDeliveryError as exc:
            unavailable.append({'uri': artifact.uri, 'reason': str(exc)})

    if not delivered:
        raise ArtifactDeliveryError(
            'no digest-verified artifacts are currently available for this run'
        )

    manifest: dict[str, Any] = {
        'schema_version': 'glasslab-artifact-delivery-v1',
        'run_id': run_id,
        'include_source': include_source,
        'artifacts': [
            {
                'archive_path': archive_name,
                'artifact_id': artifact.artifact_id,
                'job_id': artifact.job_id,
                'type': artifact.type,
                'uri': artifact.uri,
                'sha256': artifact.sha256,
                'size_bytes': len(content),
            }
            for artifact, archive_name, content in delivered
        ],
        'unavailable': unavailable,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            'artifact-manifest.json',
            json.dumps(manifest, indent=2, sort_keys=True) + '\n',
        )
        for _, archive_name, content in delivered:
            archive.writestr(archive_name, content)
    payload = output.getvalue()
    if len(payload) > maximum_bytes:
        raise ArtifactDeliveryError(
            'compressed artifact bundle exceeds the Discord delivery limit'
        )
    return ArtifactBundle(
        filename=f'glasslab-{run_id[:12]}-artifacts.zip',
        content=payload,
        artifact_count=len(delivered),
    )

