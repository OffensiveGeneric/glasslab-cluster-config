"""In-process workflow registry backed by JSON definition files on disk.

Workflows are loaded once at startup from the definitions directory; reload()
re-reads them while the process is running. The registry is the sole source of
truth for runner images, resource profiles, allowed models, evaluator types,
approval tiers, and expected artifact contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

from services.common.schemas import WorkflowRegistryEntry


class WorkflowRegistry:
    def __init__(self, registry_dir: str | Path):
        self.registry_dir = Path(registry_dir)
        self._entries = self._load_entries()

    def _load_entries(self) -> dict[str, WorkflowRegistryEntry]:
        entries: dict[str, WorkflowRegistryEntry] = {}
        for path in sorted(self.registry_dir.glob('*.json')):
            payload = json.loads(path.read_text())
            entry = WorkflowRegistryEntry.model_validate(payload)
            entries[entry.workflow_id] = entry
        return entries

    def reload(self) -> None:
        self._entries = self._load_entries()

    def list_workflows(self) -> list[WorkflowRegistryEntry]:
        return list(self._entries.values())

    def get_workflow(self, workflow_id: str) -> WorkflowRegistryEntry | None:
        return self._entries.get(workflow_id)
