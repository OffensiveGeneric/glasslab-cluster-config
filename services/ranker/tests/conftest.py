"""Test path setup for the ranker.

Inserts the service root on sys.path so tests import `app` as a top-level
package regardless of how pytest is launched.
"""

from __future__ import annotations

import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
