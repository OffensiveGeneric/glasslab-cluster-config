"""Glasslab Titanic agent API.

Legacy v1 reference implementation: normalizes a plain-English request into a
planner spec, validates it against the registries, submits a bounded Kubernetes
Job, and records authoritative state in SQLite. Superseded by
research-orchestrator but kept as the reference agent/planner/runner design.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
