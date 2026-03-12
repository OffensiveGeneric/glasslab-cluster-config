#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <experiment-id>" >&2
  exit 1
fi
BASE_URL="${AGENT_API_BASE_URL:-http://127.0.0.1:8080}"
EXPERIMENT_ID="$1"
curl -sS "${BASE_URL}/experiments/${EXPERIMENT_ID}"
printf '\n'
curl -sS "${BASE_URL}/experiments/${EXPERIMENT_ID}/logs"
printf '\n'
curl -sS "${BASE_URL}/experiments/${EXPERIMENT_ID}/artifacts"
printf '\n'
