#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '%s\n' \
  '[rollout-workflow-api-live] deprecated: use rollout-research-services.sh' >&2

exec "$ROOT_DIR/scripts/rollout-research-services.sh" \
  --service workflow-api "$@"
