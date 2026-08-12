#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/services/research-orchestrator"
PYTHON=""
for candidate in .venv/bin/python .venv314/bin/python python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
    'import enum, sys; sys.exit(0 if hasattr(enum, "StrEnum") else 1)' \
    >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "No Python 3.11+ interpreter found. Create one with:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
  exit 1
fi
PYTHONPATH=. "$PYTHON" -m app.smoke
