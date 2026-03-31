#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
SERVICE="${GLASSLAB_RESEARCH_INGRESS_SERVICE:-glasslab-research-ingress}"
LOCAL_PORT="${GLASSLAB_RESEARCH_INGRESS_LOCAL_PORT:-18096}"
CHANNEL="${GLASSLAB_RESEARCH_INGRESS_CHANNEL:-whatsapp}"
SENDER="${GLASSLAB_RESEARCH_INGRESS_SENDER:-+15555550123}"

usage() {
  cat <<'USAGE' >&2
Usage:
  research-ingress-cli.sh dispatch "<message>" [sender] [channel]
  research-ingress-cli.sh healthz

Examples:
  research-ingress-cli.sh dispatch "help:"
  research-ingress-cli.sh dispatch "research: forged art detection with computer vision methods" "+19145550123" whatsapp
  research-ingress-cli.sh dispatch "!add-paper https://arxiv.org/abs/2401.12345" "+19145550123" whatsapp
  research-ingress-cli.sh healthz
USAGE
  exit 2
}

if [[ $# -lt 1 ]]; then
  usage
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[research-ingress-cli] missing command: %s\n' "$1" >&2
    exit 1
  }
}

need_cmd kubectl
need_cmd python3

PORT_FORWARD_PID=""

cleanup() {
  if [[ -n "$PORT_FORWARD_PID" ]]; then
    kill "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

is_slow_command() {
  case "$1" in
    '!interpret'|'interpret:'|'!run'|'run:'|'!launch-iteration'|'launch-iteration:'|'!refine-notebook'|'refine-notebook:')
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

start_port_forward() {
  kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "${LOCAL_PORT}:8096" >/tmp/research-ingress-port-forward.log 2>&1 &
  PORT_FORWARD_PID=$!
  for _ in $(seq 1 40); do
    if python3 - <<PY >/dev/null 2>&1
import socket
s = socket.socket()
try:
    s.connect(("127.0.0.1", ${LOCAL_PORT}))
finally:
    s.close()
PY
    then
      return 0
    fi
    sleep 0.25
  done
  printf '[research-ingress-cli] port-forward did not become ready\n' >&2
  cat /tmp/research-ingress-port-forward.log >&2 || true
  exit 1
}

command_name="$1"
shift

start_port_forward

case "$command_name" in
  healthz)
    python3 - <<PY
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:${LOCAL_PORT}/healthz", timeout=10) as response:
    payload = json.loads(response.read().decode("utf-8"))
print(json.dumps(payload, indent=2))
PY
    ;;
  dispatch)
    [[ $# -ge 1 ]] || usage
    message="$1"
    sender="${2:-$SENDER}"
    channel="${3:-$CHANNEL}"
    if is_slow_command "$message"; then
      printf '[research-ingress-cli] waiting for %s; this command can take around 60-90s\n' "$message" >&2
    fi
    python3 - <<PY
import json
import urllib.request
import urllib.error
import urllib
import sys

payload = {
    "message": ${message@Q},
    "sender": ${sender@Q},
    "channel": ${channel@Q},
}
req = urllib.request.Request(
    "http://127.0.0.1:${LOCAL_PORT}/inbound",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=180) as response:
        body = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    print(detail, file=sys.stderr)
    sys.exit(exc.code)
except urllib.error.URLError as exc:
    print(f"request failed: {exc.reason}", file=sys.stderr)
    sys.exit(1)
print(json.dumps(body, indent=2))
PY
    ;;
  *)
    usage
    ;;
esac
