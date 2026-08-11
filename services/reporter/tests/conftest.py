"""Sys.path bootstrap for the reporter test suite.

Adds the service root (so tests can import ``app.main``) and the repository
root (so ``services.common.schemas`` resolves) before any test module imports
them. Pytest loads this file before collecting test modules, so the path
manipulation runs exactly once per test session.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = Path(__file__).resolve().parents[1]

# Both roots must be importable: `app` lives in the service, the wire schemas
# in services/common. The membership check keeps the list free of duplicates
# if conftest is ever imported more than once.
for path in (SERVICE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
