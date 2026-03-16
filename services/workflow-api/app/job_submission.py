from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from services.common.schemas import RunManifest

from .schemas import JobSubmissionReceipt


class JobSubmitter(ABC):
    @abstractmethod
    def submit_run(self, manifest: RunManifest) -> JobSubmissionReceipt:
        raise NotImplementedError


class NullJobSubmitter(JobSubmitter):
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def submit_run(self, manifest: RunManifest) -> JobSubmissionReceipt:
        return JobSubmissionReceipt(
            job_name=f'{manifest.workflow_id}-{manifest.run_id[:8]}',
            namespace=self.namespace,
            accepted_at=datetime.now(timezone.utc),
            status='accepted',
            detail='Job submission interface is present but not wired to Kubernetes yet.',
        )
