"""Shared test configuration: injects the app directory into sys.path so tests
can import from app.* without installing the package.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
