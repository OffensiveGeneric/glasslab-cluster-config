"""Runtime cluster service for bounded experiment execution.

Receives validated, policy-checked run requests from the research-orchestrator,
submits them as bounded Kubernetes Jobs, and serves observation endpoints
(status, logs, artifacts) that the orchestrator polls. This service never
originates research decisions; it is the deterministic control plane beneath
the agent layer.
"""

import sys

from .paths import discover_repo_root

REPO_ROOT = discover_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

__all__ = ['__version__']
__version__ = '0.1.0'
