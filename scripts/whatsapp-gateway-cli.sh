#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
SERVICE="${GLASSLAB_WHATSAPP_GATEWAY_SERVICE:-glasslab-whatsapp-gateway}"
LOCAL_PORT="${GLASSLAB_WHATSAPP_GATEWAY_LOCAL_PORT:-18097}"
CHANNEL="${GLASSLAB_WHATSAPP_GATEWAY_CHANNEL:-whatsapp}"
SENDER="${GLASSLAB_WHATSAPP_GATEWAY_SENDER:-+15555550123}"

usage() {
  cat <<'USAGE' >&2
Usage:
  whatsapp-gateway-cli.sh inbound "<message>" [sender] [channel]
  whatsapp-gateway-cli.sh inbound-pdf "<pdf-url>" [message] [sender] [channel]
  whatsapp-gateway-cli.sh session [sender] [channel]
  whatsapp-gateway-cli.sh healthz
USAGE
  exit 2
}

if [[ $# -lt 1 ]]; then
  usage
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[whatsapp-gateway-cli] missing command: %s\n' "$1" >&2
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

start_port_forward() {
  kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "${LOCAL_PORT}:8097" >/tmp/whatsapp-gateway-port-forward.log 2>&1 &
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
  printf '[whatsapp-gateway-cli] port-forward did not become ready\n' >&2
  cat /tmp/whatsapp-gateway-port-forward.log >&2 || true
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
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  inbound)
    [[ $# -ge 1 ]] || usage
    message="$1"
    sender="${2:-$SENDER}"
    channel="${3:-$CHANNEL}"
    python3 - <<PY
import json
import urllib.request
payload = {
    "sender": ${sender@Q},
    "channel": ${channel@Q},
    "message": ${message@Q},
    "attachments": [],
}
req = urllib.request.Request(
    "http://127.0.0.1:${LOCAL_PORT}/webhooks/whatsapp/inbound",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  inbound-pdf)
    [[ $# -ge 1 ]] || usage
    pdf_url="$1"
    message="${2:-}"
    sender="${3:-$SENDER}"
    channel="${4:-$CHANNEL}"
    python3 - <<PY
import json
import urllib.request
payload = {
    "sender": ${sender@Q},
    "channel": ${channel@Q},
    "message": ${message@Q},
    "attachments": [{
        "url": ${pdf_url@Q},
        "mime_type": "application/pdf",
        "filename": "attachment.pdf",
    }],
}
req = urllib.request.Request(
    "http://127.0.0.1:${LOCAL_PORT}/webhooks/whatsapp/inbound",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  session)
    sender="${1:-$SENDER}"
    channel="${2:-$CHANNEL}"
    python3 - <<PY
import json
import urllib.parse
import urllib.request
sender = urllib.parse.quote(${sender@Q}, safe="")
channel = urllib.parse.quote(${channel@Q}, safe="")
with urllib.request.urlopen(f"http://127.0.0.1:${LOCAL_PORT}/sessions/{channel}/{sender}", timeout=10) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  *)
    usage
    ;;
esac
