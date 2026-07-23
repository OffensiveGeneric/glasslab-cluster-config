#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
CURL="${CURL:-curl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
LOCAL_PORT="${GLASSLAB_WORKFLOW_API_PORT:-18081}"
PORT_FORWARD_PID=""
PORT_FORWARD_LOG=""

usage() {
  cat <<'USAGE'
Usage:
  research-session-cli.sh start "goal statement"
  research-session-cli.sh new "goal statement"
  research-session-cli.sh literature-start "goal statement"
  research-session-cli.sh context
  research-session-cli.sh next-paper
  research-session-cli.sh note "text"
  research-session-cli.sh op

Deterministic CLI wrapper for the session-centered research loop.

This talks directly to workflow-api through a temporary kubectl port-forward
instead of depending on OpenClaw tool selection.
USAGE
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[research-session-cli] missing command: %s\n' "$1" >&2
    exit 1
  }
}

cleanup() {
  if [[ -n "$PORT_FORWARD_PID" ]]; then
    kill "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
  if [[ -n "$PORT_FORWARD_LOG" && -f "$PORT_FORWARD_LOG" ]]; then
    rm -f "$PORT_FORWARD_LOG"
  fi
}
trap cleanup EXIT

start_port_forward() {
  PORT_FORWARD_LOG="$(mktemp)"
  "$KUBECTL" -n "$NAMESPACE" port-forward svc/glasslab-workflow-api "${LOCAL_PORT}:8080" >"$PORT_FORWARD_LOG" 2>&1 &
  PORT_FORWARD_PID="$!"
  for _ in $(seq 1 30); do
    if "$CURL" -fsS "http://127.0.0.1:${LOCAL_PORT}/healthz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  printf '[research-session-cli] workflow-api port-forward did not become ready\n' >&2
  cat "$PORT_FORWARD_LOG" >&2 || true
  exit 1
}

api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  if [[ -n "$body" ]]; then
    "$CURL" -fsS -X "$method" "http://127.0.0.1:${LOCAL_PORT}${path}" \
      -H 'content-type: application/json' \
      --data "$body"
  else
    "$CURL" -fsS -X "$method" "http://127.0.0.1:${LOCAL_PORT}${path}"
  fi
}

extract_json_field() {
  local field="$1"
  python3 -c 'import json,sys; value=json.loads(sys.stdin.read())
for segment in sys.argv[1].split("."): value=value[segment]
print(value if isinstance(value,str) else json.dumps(value))' "$field"
}

pretty_print() {
  python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read()), indent=2))'
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

main() {
  need_cmd "$KUBECTL"
  need_cmd "$CURL"
  need_cmd python3

  local command="${1:-}"
  if [[ -z "$command" ]]; then
    usage >&2
    exit 2
  fi
  shift || true

  start_port_forward

  case "$command" in
    start|new)
      local goal="${1:-}"
      [[ -n "$goal" ]] || {
        printf '[research-session-cli] %s requires a goal statement\n' "$command" >&2
        exit 2
      }
      api POST /research-sessions \
        "{\"goal_statement\":$(json_escape "$goal"),\"priorities\":[],\"submitted_by\":\"research-session-cli\"}" \
        | pretty_print
      ;;
    literature-start)
      local goal="${1:-}"
      [[ -n "$goal" ]] || {
        printf '[research-session-cli] literature-start requires a goal statement\n' >&2
        exit 2
      }
      printf '[research-session-cli] warning: literature-start is deprecated; prefer OpenCode plus direct run scripts\n' >&2
      api POST /research-sessions/start-literature-search \
        "{\"goal_statement\":$(json_escape "$goal"),\"priorities\":[],\"submitted_by\":\"research-session-cli\"}" \
        | pretty_print
      ;;
    context)
      api GET /research-sessions/latest/context | pretty_print
      ;;
    next-paper)
      local queue_id
      queue_id="$(
        api GET /research-sessions/latest/context | extract_json_field "paper_intake_queue.queue_id"
      )"
      api POST "/paper-intake-queues/${queue_id}/stage-next-intake" | pretty_print
      ;;
    note)
      local note="${1:-}"
      [[ -n "$note" ]] || {
        printf '[research-session-cli] note requires text\n' >&2
        exit 2
      }
      api POST /research-sessions/latest/memory \
        "{\"working_note\":$(json_escape "$note")}" \
        | pretty_print
      ;;
    op)
      api GET /operations/latest | pretty_print
      ;;
    *)
      printf '[research-session-cli] unknown command: %s\n' "$command" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
