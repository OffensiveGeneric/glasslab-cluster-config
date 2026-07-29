from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from .schemas import IngestedDatasetRecord
from .storage import RecordNotFound, SqliteStore
from .task_bundles import DatasetAsset, TaskBundleError


class DatasetIngestionError(ValueError):
    pass


class DatasetIngestionManager:
    """Stores immutable uploads and resolves stable dataset references."""

    _NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')

    def __init__(
        self,
        *,
        store: SqliteStore,
        root: str,
        shared_mount_root: str,
        maximum_bytes: int,
    ) -> None:
        self.store = store
        self.root = Path(root).resolve()
        self.shared_mount_root = Path(shared_mount_root).resolve()
        self.maximum_bytes = maximum_bytes
        if not self.root.is_relative_to(self.shared_mount_root):
            raise DatasetIngestionError(
                'dataset upload root must be inside the shared mount'
            )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        value = Path(filename).name.strip()
        if (
            not value
            or value in {'.', '..'}
            or len(value) > 255
            or any(character in value for character in ('\x00', '/', '\\'))
        ):
            raise DatasetIngestionError('dataset filename is invalid')
        return value

    @classmethod
    def _safe_name(cls, name: str) -> str:
        value = name.strip().lower().replace(' ', '_')
        if not cls._NAME_PATTERN.fullmatch(value):
            raise DatasetIngestionError(
                'dataset name must use lowercase letters, numbers, _ or -'
            )
        return value

    def ingest(
        self,
        source: BinaryIO,
        *,
        filename: str,
        name: str,
        role: str = 'input',
        contains_labels: bool = False,
        media_type: str | None = None,
        uploaded_by: str | None = None,
    ) -> IngestedDatasetRecord:
        safe_filename = self._safe_filename(filename)
        safe_name = self._safe_name(name)
        if not role.strip():
            raise DatasetIngestionError('dataset role is required')
        self.root.mkdir(parents=True, exist_ok=True)
        digest = sha256()
        size = 0
        with NamedTemporaryFile(dir=self.root, delete=False) as staged:
            staged_path = Path(staged.name)
            try:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.maximum_bytes:
                        raise DatasetIngestionError(
                            'dataset exceeds the configured upload size limit'
                        )
                    digest.update(chunk)
                    staged.write(chunk)
            except Exception:
                staged_path.unlink(missing_ok=True)
                raise
        if size == 0:
            staged_path.unlink(missing_ok=True)
            raise DatasetIngestionError('dataset is empty')

        actual_digest = digest.hexdigest()
        try:
            existing = self.store.get_dataset(actual_digest)
        except RecordNotFound:
            existing = None
        if existing is not None:
            staged_path.unlink(missing_ok=True)
            if existing.contains_labels != contains_labels:
                raise DatasetIngestionError(
                    'dataset content already exists with a different label '
                    'declaration'
                )
            return existing

        destination = self.root / actual_digest / safe_filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            staged_path.unlink(missing_ok=True)
        else:
            os.replace(staged_path, destination)
        destination.chmod(0o444)
        destination.parent.chmod(0o555)
        artifact_uri = (
            's3://artifacts/'
            + destination.relative_to(self.shared_mount_root).as_posix()
        )
        record = IngestedDatasetRecord(
            dataset_id=actual_digest,
            name=safe_name,
            filename=safe_filename,
            reference_uri=f'glasslab-dataset://{actual_digest}',
            artifact_uri=artifact_uri,
            path=str(destination),
            sha256=actual_digest,
            size_bytes=size,
            media_type=media_type,
            role=role.strip(),
            contains_labels=contains_labels,
            uploaded_by=uploaded_by,
        )
        return self.store.save_dataset(record)

    def ingest_bytes(self, content: bytes, **metadata) -> IngestedDatasetRecord:
        from io import BytesIO

        return self.ingest(BytesIO(content), **metadata)

    def resolve(
        self,
        reference_uri: str,
        *,
        name: str,
        role: str,
        contains_labels: bool,
        expected_sha256: str | None = None,
    ) -> DatasetAsset:
        prefix = 'glasslab-dataset://'
        if not reference_uri.startswith(prefix):
            raise TaskBundleError('dataset reference is not approved')
        dataset_id = reference_uri.removeprefix(prefix)
        try:
            record = self.store.get_dataset(dataset_id)
        except RecordNotFound as exc:
            raise TaskBundleError(
                f'ingested dataset is not registered: {reference_uri}'
            ) from exc
        path = Path(record.path).resolve()
        if (
            not path.is_relative_to(self.root)
            or not path.is_file()
            or path.stat().st_size != record.size_bytes
        ):
            raise TaskBundleError(
                f'ingested dataset is unavailable: {reference_uri}'
            )
        actual_digest = self._file_sha256(path)
        if actual_digest != record.sha256:
            raise TaskBundleError(
                f'ingested dataset failed checksum verification: {reference_uri}'
            )
        if expected_sha256 and expected_sha256 != record.sha256:
            raise TaskBundleError(
                f'ingested dataset checksum does not match proposal: {name}'
            )
        if contains_labels != record.contains_labels:
            raise TaskBundleError(
                f'ingested dataset label declaration does not match registry: '
                f'{name}'
            )
        return DatasetAsset(
            name=name,
            uri=record.artifact_uri,
            sha256=record.sha256,
            role=role,
            contains_labels=record.contains_labels,
        )

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()
