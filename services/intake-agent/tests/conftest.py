"""Test path setup for the intake-agent service.

The service has no installable package metadata, so the service root and the
repo root are inserted into sys.path before any test module is imported,
keeping the checkout importable regardless of how pytest is launched.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

for path in (SERVICE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
