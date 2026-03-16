from __future__ import annotations

from pathlib import Path


def discover_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / 'services' / 'workflow-registry' / 'definitions').exists():
            return parent
    return current.parents[1]
