"""Test setup for the agent-api package.

Puts the service root on sys.path so tests import `app` as a top-level package
regardless of how pytest is launched.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
