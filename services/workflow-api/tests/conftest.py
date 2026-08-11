"""Make the workflow-api ``app`` package importable from the tests directory.

Adds both the service root (for ``import app.*``) and the repo root
(for ``import services.common.*``) to ``sys.path``.  Individual test
modules are responsible for clearing cached ``app.*`` modules before
re-importing — that step lives in the test files, not here, because
Pytest's collection phase runs conftest before any test module sees
``sys.modules``.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

for path in (SERVICE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
