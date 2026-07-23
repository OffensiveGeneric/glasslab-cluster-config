#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

HELPER="${GLASSLAB_OPENCODE_HELPER:-}"
if [[ -z "$HELPER" ]]; then
  if command -v opencode-with-exo >/dev/null 2>&1; then
    HELPER="$(command -v opencode-with-exo)"
  else
    HELPER="${HOME}/.local/bin/opencode-with-exo"
  fi
fi

OPENCODE_BIN="${OPENCODE_BIN:-}"
if [[ -z "$OPENCODE_BIN" ]]; then
  if command -v opencode >/dev/null 2>&1; then
    OPENCODE_BIN="$(command -v opencode)"
  else
    OPENCODE_BIN="${HOME}/.npm-global/bin/opencode"
  fi
fi

API_BASE="${GLASSLAB_EXO_API_BASE:-http://192.168.1.18:52415}"
MODEL="${GLASSLAB_OPENCODE_MODEL:-mlx-community/Qwen3-Coder-Next-4bit}"

if [[ ! -x "$HELPER" ]]; then
  printf '[glasslab-opencode] helper not executable: %s\n' "$HELPER" >&2
  exit 1
fi

if [[ ! -x "$OPENCODE_BIN" ]]; then
  printf '[glasslab-opencode] opencode not executable: %s\n' "$OPENCODE_BIN" >&2
  exit 1
fi

export OPENCODE_BIN
export PATH="$(dirname "$OPENCODE_BIN"):${PATH}"

cd "$REPO_DIR"
exec "$HELPER" --api "$API_BASE" --model "$MODEL" "$@"
