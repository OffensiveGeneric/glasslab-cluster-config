from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from typing import Any
from uuid import uuid4
import zipfile

from pydantic import BaseModel, ConfigDict, Field


class TaskBundleError(ValueError):
    pass


class DatasetAsset(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    uri: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    role: str
    contains_labels: bool = False


class TaskBundleRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    task_id: str
    display_name: str
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    archive_uri: str
    archive_path: str
    problem_path: str
    evaluator_prompt_path: str
    workload_id: str
    experiment_type: str
    runner_image: str
    command: list[str]
    source_subdirectory: str
    default_contract_id: str
    default_contract_version: str
    resources: dict[str, Any]
    required_artifacts: list[str]
    datasets: list[DatasetAsset]


@dataclass(frozen=True)
class _TaskTemplate:
    task_id: str
    display_name: str
    archive_names: tuple[str, ...]
    workload_id: str
    runner_image: str
    default_contract_id: str
    resources: dict[str, Any]
    required_artifacts: tuple[str, ...]
    dataset_names: tuple[str, ...]


BASE_REQUIRED_ARTIFACTS = (
    'run_manifest.json',
    'config.json',
    'metrics.json',
    'evaluation.json',
    'artifacts_index.json',
    'report.md',
    'status.json',
    'logs/',
    'source.zip',
)

TASK_TEMPLATES = (
    _TaskTemplate(
        task_id='adult-income',
        display_name='UCI Adult Income Classification',
        archive_names=('ML_Benchmark_Adult_Income.zip',),
        workload_id='benchmark-workspace-cpu-v1',
        runner_image=(
            'ghcr.io/offensivegeneric/'
            'glasslab-research-workspace-runner:benchmark-cpu-v1'
        ),
        default_contract_id='ml-benchmark-adult-income-v1',
        resources={
            'cpu': 4,
            'memory_gib': 8,
            'gpus': 0,
            'wallclock_minutes': 60,
        },
        required_artifacts=BASE_REQUIRED_ARTIFACTS
        + ('tables/metrics.csv', 'tables/fairness.csv'),
        dataset_names=('adult_train', 'adult_test'),
    ),
    _TaskTemplate(
        task_id='wine-clustering',
        display_name='UCI Wine Multi-Algorithm Clustering',
        archive_names=('ML_Benchmark_Wine_Clustering.zip',),
        workload_id='benchmark-workspace-cpu-v1',
        runner_image=(
            'ghcr.io/offensivegeneric/'
            'glasslab-research-workspace-runner:benchmark-cpu-v1'
        ),
        default_contract_id='ml-benchmark-wine-clustering-v1',
        resources={
            'cpu': 4,
            'memory_gib': 8,
            'gpus': 0,
            'wallclock_minutes': 45,
        },
        required_artifacts=BASE_REQUIRED_ARTIFACTS
        + ('plots/clusters.png', 'tables/comparison.csv'),
        dataset_names=('wine',),
    ),
    _TaskTemplate(
        task_id='fashion-mnist-contrastive',
        display_name='Fashion-MNIST Contrastive Representation Learning',
        archive_names=('ML_Benchmark_FashionMNIST_Contrastive.zip',),
        workload_id='benchmark-workspace-gpu-v1',
        runner_image=(
            'ghcr.io/offensivegeneric/'
            'glasslab-research-workspace-runner:benchmark-gpu-v1'
        ),
        default_contract_id='ml-benchmark-fashion-contrastive-v1',
        resources={
            'cpu': 8,
            'memory_gib': 32,
            'gpus': 1,
            'wallclock_minutes': 240,
        },
        required_artifacts=BASE_REQUIRED_ARTIFACTS
        + (
            'plots/training_curve.png',
            'plots/embeddings.png',
            'tables/class_metrics.csv',
        ),
        dataset_names=('fashion_mnist',),
    ),
)


class TaskBundleManager:
    MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
    MAX_FILES = 16
    MAX_EXPANDED_BYTES = 4 * 1024 * 1024

    def __init__(
        self,
        *,
        root: str,
        shared_mount_root: str,
        dataset_catalog_path: str,
    ) -> None:
        self.root = Path(root).resolve()
        self.shared_mount_root = Path(shared_mount_root).resolve()
        self.dataset_catalog_path = Path(dataset_catalog_path).resolve()

    @staticmethod
    def templates() -> dict[str, _TaskTemplate]:
        return {item.task_id: item for item in TASK_TEMPLATES}

    @staticmethod
    def _template_for_archive(filename: str) -> _TaskTemplate:
        for template in TASK_TEMPLATES:
            if filename in template.archive_names:
                return template
        supported = ', '.join(
            name for item in TASK_TEMPLATES for name in item.archive_names
        )
        raise TaskBundleError(
            f'unsupported benchmark archive {filename!r}; expected one of {supported}'
        )

    def _load_dataset_catalog(self) -> dict[str, dict[str, Any]]:
        if not self.dataset_catalog_path.is_file():
            raise TaskBundleError(
                'benchmark dataset catalog is not staged on the shared volume'
            )
        parsed = json.loads(
            self.dataset_catalog_path.read_text(encoding='utf-8')
        )
        if not isinstance(parsed, dict):
            raise TaskBundleError('benchmark dataset catalog is invalid')
        return parsed

    def import_archive(
        self,
        *,
        filename: str,
        content: bytes,
    ) -> TaskBundleRecord:
        template = self._template_for_archive(Path(filename).name)
        if not content or len(content) > self.MAX_ARCHIVE_BYTES:
            raise TaskBundleError('benchmark archive has an invalid size')
        digest = sha256(content).hexdigest()
        destination = self.root / template.task_id / digest
        metadata_path = destination / 'task.json'
        if metadata_path.is_file():
            return TaskBundleRecord.model_validate_json(
                metadata_path.read_text(encoding='utf-8')
            )
        staging = self.root / '.staging' / uuid4().hex
        staging.mkdir(parents=True, exist_ok=False)
        archive_path = staging / 'task.zip'
        archive_path.write_bytes(content)
        try:
            with zipfile.ZipFile(archive_path) as handle:
                files = [item for item in handle.infolist() if not item.is_dir()]
                if not files or len(files) > self.MAX_FILES:
                    raise TaskBundleError('benchmark archive file count is invalid')
                expanded = 0
                for member in files:
                    path = PurePosixPath(member.filename)
                    mode = member.external_attr >> 16
                    if (
                        path.is_absolute()
                        or '..' in path.parts
                        or mode & 0o170000 == 0o120000
                    ):
                        raise TaskBundleError(
                            f'unsafe benchmark archive member: {member.filename}'
                        )
                    expanded += member.file_size
                if expanded > self.MAX_EXPANDED_BYTES:
                    raise TaskBundleError('benchmark archive expands too large')
                problem_members = [
                    item for item in files if PurePosixPath(item.filename).name == 'problem.md'
                ]
                evaluator_members = [
                    item
                    for item in files
                    if PurePosixPath(item.filename).name == 'eval_agent_prompt.md'
                ]
                if len(problem_members) != 1 or len(evaluator_members) != 1:
                    raise TaskBundleError(
                        'benchmark archive requires one problem.md and one '
                        'eval_agent_prompt.md'
                    )
                normalized = staging / 'normalized'
                normalized.mkdir()
                problem = normalized / 'problem.md'
                evaluator = normalized / 'eval_agent_prompt.md'
                problem.write_bytes(handle.read(problem_members[0]))
                evaluator.write_bytes(handle.read(evaluator_members[0]))
        except zipfile.BadZipFile as exc:
            raise TaskBundleError('benchmark task must be a ZIP archive') from exc

        dataset_catalog = self._load_dataset_catalog()
        datasets: list[DatasetAsset] = []
        for name in template.dataset_names:
            entry = dataset_catalog.get(name)
            if not isinstance(entry, dict):
                raise TaskBundleError(f'dataset is not staged: {name}')
            datasets.append(DatasetAsset.model_validate({'name': name, **entry}))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(staging)
        else:
            os.replace(staging, destination)
        record = TaskBundleRecord(
            task_id=template.task_id,
            display_name=template.display_name,
            digest=digest,
            archive_uri=(
                's3://artifacts/'
                + (destination / 'task.zip')
                .relative_to(self.shared_mount_root)
                .as_posix()
            ),
            archive_path=str(destination / 'task.zip'),
            problem_path=str(destination / 'normalized' / 'problem.md'),
            evaluator_prompt_path=str(
                destination / 'normalized' / 'eval_agent_prompt.md'
            ),
            workload_id=template.workload_id,
            experiment_type='research-workspace-job',
            runner_image=template.runner_image,
            command=['python3', 'run.py'],
            source_subdirectory=f'benchmark-workspace/{template.task_id}',
            default_contract_id=template.default_contract_id,
            default_contract_version='1.0.0',
            resources=template.resources,
            required_artifacts=list(template.required_artifacts),
            datasets=datasets,
        )
        metadata_path = destination / 'task.json'
        metadata_path.write_text(
            record.model_dump_json(indent=2) + '\n',
            encoding='utf-8',
        )
        for path in destination.rglob('*'):
            path.chmod(0o555 if path.is_dir() else 0o444)
        return record

    def get(self, task_id: str, digest: str | None = None) -> TaskBundleRecord:
        task_root = (self.root / task_id).resolve()
        if not task_root.is_relative_to(self.root) or not task_root.is_dir():
            raise TaskBundleError(f'task bundle is not imported: {task_id}')
        candidates = sorted(
            (path for path in task_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if digest:
            candidates = [path for path in candidates if path.name == digest]
        if not candidates:
            raise TaskBundleError(f'task bundle digest is not imported: {task_id}')
        return TaskBundleRecord.model_validate_json(
            (candidates[0] / 'task.json').read_text(encoding='utf-8')
        )

    def list(self) -> list[TaskBundleRecord]:
        records: list[TaskBundleRecord] = []
        if not self.root.is_dir():
            return records
        for task_root in sorted(self.root.iterdir()):
            if not task_root.is_dir() or task_root.name.startswith('.'):
                continue
            try:
                records.append(self.get(task_root.name))
            except (OSError, ValueError):
                continue
        return records
