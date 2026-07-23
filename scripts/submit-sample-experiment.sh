#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OBJECTIVE="${1:-Run a bounded metric-search sample learning task.}"

printf '[submit-sample-experiment] compatibility wrapper; use submit-learning-task.sh for new work\n' >&2
exec "${SCRIPT_DIR}/submit-learning-task.sh" "$OBJECTIVE"
