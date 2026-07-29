from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from .contracts import (
    ContractIntegrityError,
    compute_contract_digest,
)
from .schemas import EvaluationContractDescriptor


class ContractCandidateError(ValueError):
    pass


@dataclass(frozen=True)
class SealedContractCandidate:
    contract_id: str
    version: str
    digest: str
    sealed_path: Path
    descriptor: EvaluationContractDescriptor


class ContractCandidateManager:
    MAX_FILES = 64
    MAX_TOTAL_BYTES = 2 * 1024 * 1024
    ALLOWED_SUFFIXES = {'.json', '.md', '.py', '.txt'}

    def __init__(
        self,
        *,
        sealed_root: str,
        promoted_root: str,
        catalog_path: str,
        shared_mount_root: str,
    ) -> None:
        self.sealed_root = Path(sealed_root).resolve()
        self.promoted_root = Path(promoted_root).resolve()
        self.catalog_path = Path(catalog_path).resolve()
        self.shared_mount_root = Path(shared_mount_root).resolve()

    @staticmethod
    def _validate_source_tree(source: Path) -> list[Path]:
        if source.is_symlink() or not source.is_dir():
            raise ContractCandidateError(
                'contract candidate must be a real directory'
            )
        files: list[Path] = []
        total_bytes = 0
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ContractCandidateError(
                    f'contract candidate cannot contain symlinks: {path}'
                )
            if path.is_dir():
                continue
            relative = path.relative_to(source)
            if (
                '__pycache__' in relative.parts
                or relative.name == 'contract.sha256'
                or path.suffix not in ContractCandidateManager.ALLOWED_SUFFIXES
            ):
                raise ContractCandidateError(
                    f'unsupported contract candidate file: {relative}'
                )
            files.append(path)
            total_bytes += path.stat().st_size
        if not files:
            raise ContractCandidateError('contract candidate is empty')
        if len(files) > ContractCandidateManager.MAX_FILES:
            raise ContractCandidateError('contract candidate has too many files')
        if total_bytes > ContractCandidateManager.MAX_TOTAL_BYTES:
            raise ContractCandidateError('contract candidate is too large')
        return files

    @staticmethod
    def _validate_descriptor(
        root: Path,
        *,
        contract_id: str,
        version: str,
    ) -> EvaluationContractDescriptor:
        descriptor_path = root / 'contract.json'
        if not descriptor_path.is_file():
            raise ContractCandidateError('candidate is missing contract.json')
        try:
            descriptor = EvaluationContractDescriptor.model_validate_json(
                descriptor_path.read_text(encoding='utf-8')
            )
        except Exception as exc:
            raise ContractCandidateError(
                f'candidate contract.json is invalid: {exc}'
            ) from exc
        if descriptor.contract_id != contract_id or descriptor.version != version:
            raise ContractCandidateError(
                'candidate descriptor identity does not match the proposal'
            )
        if descriptor.container_image_digest is not None:
            raise ContractCandidateError(
                'shared-bundle candidates cannot choose a container image'
            )
        primary_metric = str(descriptor.manifest.get('primary_metric', '')).strip()
        direction = str(
            descriptor.manifest.get('primary_metric_direction', '')
        ).strip()
        if not primary_metric or direction not in {'maximize', 'minimize'}:
            raise ContractCandidateError(
                'manifest requires primary_metric and a valid direction'
            )
        try:
            for field in (
                descriptor.execution_wrapper,
                descriptor.evaluation_entry_point,
                descriptor.expected_input_schema,
                descriptor.expected_output_schema,
            ):
                target = (root / field).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    raise ContractCandidateError(
                        f'candidate references missing file: {field}'
                    )
            for schema_path in (
                descriptor.expected_input_schema,
                descriptor.expected_output_schema,
            ):
                parsed = json.loads((root / schema_path).read_text(encoding='utf-8'))
                if not isinstance(parsed, dict):
                    raise ContractCandidateError(
                        f'JSON schema must be an object: {schema_path}'
                    )
            for python_path in (
                descriptor.execution_wrapper,
                descriptor.evaluation_entry_point,
            ):
                ast.parse(
                    (root / python_path).read_text(encoding='utf-8'),
                    filename=python_path,
                )
        except (OSError, ValueError, SyntaxError, json.JSONDecodeError) as exc:
            raise ContractCandidateError(str(exc)) from exc
        return descriptor

    def seal(
        self,
        *,
        source: Path,
        contract_id: str,
        version: str,
    ) -> SealedContractCandidate:
        self._validate_source_tree(source)
        descriptor = self._validate_descriptor(
            source,
            contract_id=contract_id,
            version=version,
        )
        staging_parent = self.sealed_root / '.staging'
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging = staging_parent / uuid4().hex
        shutil.copytree(source, staging)
        digest = compute_contract_digest(staging)
        (staging / 'contract.sha256').write_text(digest + '\n', encoding='ascii')
        destination = self.sealed_root / contract_id / version / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(staging)
        else:
            os.replace(staging, destination)
        for path in destination.rglob('*'):
            path.chmod(0o555 if path.is_dir() else 0o444)
        return SealedContractCandidate(
            contract_id=contract_id,
            version=version,
            digest=digest,
            sealed_path=destination,
            descriptor=descriptor,
        )

    def verify_seal(
        self,
        *,
        sealed_path: Path,
        expected_digest: str,
    ) -> EvaluationContractDescriptor:
        path = sealed_path.resolve()
        if not path.is_relative_to(self.sealed_root):
            raise ContractCandidateError('sealed candidate escapes candidate root')
        expected = (path / 'contract.sha256').read_text().strip()
        actual = compute_contract_digest(path)
        if expected != expected_digest or actual != expected_digest:
            raise ContractIntegrityError('sealed candidate digest mismatch')
        return EvaluationContractDescriptor.model_validate_json(
            (path / 'contract.json').read_text()
        )

    def promote(
        self,
        *,
        sealed_path: Path,
        expected_digest: str,
    ) -> Path:
        descriptor = self.verify_seal(
            sealed_path=sealed_path,
            expected_digest=expected_digest,
        )
        destination = (
            self.promoted_root / descriptor.contract_id / descriptor.version
        )
        if destination.exists():
            existing = compute_contract_digest(destination)
            if existing != expected_digest:
                raise ContractCandidateError(
                    'contract version is already promoted with another digest'
                )
        else:
            staging = destination.parent / f'.{descriptor.version}.{uuid4().hex}'
            staging.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(sealed_path, staging)
            os.replace(staging, destination)
        for path in destination.rglob('*'):
            path.chmod(0o555 if path.is_dir() else 0o444)
        self._write_catalog_entry(
            descriptor=descriptor,
            digest=expected_digest,
            promoted_path=destination,
        )
        return destination

    def _write_catalog_entry(
        self,
        *,
        descriptor: EvaluationContractDescriptor,
        digest: str,
        promoted_path: Path,
    ) -> None:
        if not promoted_path.is_relative_to(self.shared_mount_root):
            raise ContractCandidateError(
                'promoted contract is outside the shared mount root'
            )
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog: dict[str, dict[str, str]] = {}
        if self.catalog_path.is_file():
            parsed = json.loads(self.catalog_path.read_text(encoding='utf-8'))
            if not isinstance(parsed, dict):
                raise ContractCandidateError('trusted contract catalog is invalid')
            catalog = parsed
        key = f'{descriptor.contract_id}@{descriptor.version}'
        catalog[key] = {
            'contract_id': descriptor.contract_id,
            'version': descriptor.version,
            'digest': digest,
            'bundle_path': promoted_path.relative_to(
                self.shared_mount_root
            ).as_posix(),
            'execution_wrapper': descriptor.execution_wrapper,
            'evaluation_entry_point': descriptor.evaluation_entry_point,
        }
        temporary = self.catalog_path.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(catalog, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        os.replace(temporary, self.catalog_path)
