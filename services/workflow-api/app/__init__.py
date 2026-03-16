"""Glasslab v2 workflow API."""

import sys

from .paths import discover_repo_root

REPO_ROOT = discover_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

__all__ = ['__version__']
__version__ = '0.1.0'
