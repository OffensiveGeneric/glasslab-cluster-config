#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
API_KEY="${VLLM_API_KEY:-change-me}"
curl -sS -H "Authorization: Bearer ${API_KEY}" "${BASE_URL}/models"
printf '\n'
curl -sS \
  -H "Authorization: Bearer ${API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-4B-Instruct-2507","messages":[{"role":"user","content":"Return valid JSON only: {\"ok\": true}"}],"temperature":0.0,"max_tokens":64}' \
  "${BASE_URL}/chat/completions"
printf '\n'
