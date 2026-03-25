#!/bin/bash
set -euo pipefail

MODEL="${GLASSLAB_OLLAMA_PULL_MODEL:-qwen3:30b}"
OLLAMA_BIN="${GLASSLAB_OLLAMA_BIN:-/Applications/Ollama.app/Contents/Resources/ollama}"
PULL_LOG="${GLASSLAB_OLLAMA_PULL_LOG:-/tmp/ollama-pull-qwen3-30b.log}"
WATCHDOG_LOG="${GLASSLAB_OLLAMA_WATCHDOG_LOG:-/tmp/ollama-pull-watchdog.log}"
STALL_SECONDS="${GLASSLAB_OLLAMA_PULL_STALL_SECONDS:-180}"
STATE_DIR="${GLASSLAB_OLLAMA_WATCHDOG_STATE_DIR:-$HOME/Library/Application Support/glasslab/ollama-watchdog}"
STATE_FILE="$STATE_DIR/${MODEL//[:\/ ]/_}.state"

mkdir -p "$STATE_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$WATCHDOG_LOG"
}

get_log_size() {
  if [[ -f "$PULL_LOG" ]]; then
    stat -f '%z' "$PULL_LOG"
  else
    printf '0'
  fi
}

get_progress_mb() {
  if [[ ! -f "$PULL_LOG" ]]; then
    return 0
  fi

  perl -ne 'while (/([0-9]+)\s*MB\/\s*[0-9]+\s*GB/g) { $last = $1 } END { print $last if defined $last }' "$PULL_LOG"
}

is_installed() {
  "$OLLAMA_BIN" list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fxq "$MODEL"
}

pull_running() {
  pgrep -f "ollama pull $MODEL" >/dev/null 2>&1
}

restart_pull() {
  pkill -f "ollama pull $MODEL" >/dev/null 2>&1 || true
  nohup "$OLLAMA_BIN" pull "$MODEL" >"$PULL_LOG" 2>&1 </dev/null &
  log "restarted pull for $MODEL"
}

LAST_PROGRESS_MB=""
LAST_LOG_SIZE=""
LAST_CHANGE_EPOCH="0"

if [[ -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
fi

NOW_EPOCH="$(date '+%s')"
CURRENT_LOG_SIZE="$(get_log_size)"
CURRENT_PROGRESS_MB="$(get_progress_mb || true)"

if is_installed; then
  log "$MODEL already installed; watchdog exiting"
  exit 0
fi

if ! pull_running; then
  log "pull process for $MODEL is not running; starting it"
  restart_pull
  cat >"$STATE_FILE" <<EOF
LAST_PROGRESS_MB=${CURRENT_PROGRESS_MB:-0}
LAST_LOG_SIZE=$CURRENT_LOG_SIZE
LAST_CHANGE_EPOCH=$NOW_EPOCH
EOF
  exit 0
fi

if [[ "${CURRENT_PROGRESS_MB:-}" != "${LAST_PROGRESS_MB:-}" || "$CURRENT_LOG_SIZE" != "${LAST_LOG_SIZE:-}" ]]; then
  cat >"$STATE_FILE" <<EOF
LAST_PROGRESS_MB=${CURRENT_PROGRESS_MB:-0}
LAST_LOG_SIZE=$CURRENT_LOG_SIZE
LAST_CHANGE_EPOCH=$NOW_EPOCH
EOF
  log "progress advanced for $MODEL to ${CURRENT_PROGRESS_MB:-0} MB"
  exit 0
fi

AGE=$((NOW_EPOCH - LAST_CHANGE_EPOCH))
if (( AGE >= STALL_SECONDS )); then
  log "detected stalled pull for $MODEL after ${AGE}s at ${CURRENT_PROGRESS_MB:-0} MB; restarting"
  restart_pull
  cat >"$STATE_FILE" <<EOF
LAST_PROGRESS_MB=${CURRENT_PROGRESS_MB:-0}
LAST_LOG_SIZE=$CURRENT_LOG_SIZE
LAST_CHANGE_EPOCH=$NOW_EPOCH
EOF
  exit 0
fi

log "no progress change for $MODEL yet, but still within stall window (${AGE}s < ${STALL_SECONDS}s)"
