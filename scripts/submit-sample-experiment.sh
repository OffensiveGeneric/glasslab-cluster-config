#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${AGENT_API_BASE_URL:-http://127.0.0.1:8080}"
curl -sS \
  -H 'Content-Type: application/json' \
  -d '{"request_text":"Run a Titanic baseline with logistic regression and random forest, compare them, and prepare a submission file."}' \
  "${BASE_URL}/experiments"
printf '\n'
