"""Filesystem location utilities for the workflow-api service.

Shipped images do not inherit the developer's working directory, so all
path-based configuration must be resolved relative to a discovered repo root
rather than a hard-coded prefix.
"""

from __future__ import annotations

from pathlib import Path


def discover_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / 'services' / 'workflow-registry' / 'definitions').exists():
            return parent
    return current.parents[1]
