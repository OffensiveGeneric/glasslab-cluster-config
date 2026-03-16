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
