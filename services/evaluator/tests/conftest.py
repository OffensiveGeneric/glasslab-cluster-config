"""Test path setup for the evaluator service.

The service has no installable package metadata, so tests must be able to import
`app` and `services.common` from a plain checkout: both the service root and the
repo root are inserted into sys.path before any test module is imported.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = Path(__file__).resolve().parents[1]

for path in (SERVICE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
