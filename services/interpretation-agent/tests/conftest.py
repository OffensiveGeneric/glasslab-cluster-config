"""Test path setup for the interpretation agent.

Inserts the service root and the repo root on sys.path so shared packages
resolve regardless of how pytest is launched.
"""

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

for path in (SERVICE_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
