#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
SERVICE="${GLASSLAB_WHATSAPP_GATEWAY_SERVICE:-glasslab-whatsapp-gateway}"
LOCAL_PORT="${GLASSLAB_WHATSAPP_GATEWAY_LOCAL_PORT:-18097}"
CHANNEL="${GLASSLAB_WHATSAPP_GATEWAY_CHANNEL:-whatsapp}"
SENDER="${GLASSLAB_WHATSAPP_GATEWAY_SENDER:-+15555550123}"
ACTIVE_LOCAL_PORT=""
PORT_FORWARD_LOG=""

usage() {
  cat <<'USAGE' >&2
Usage:
  whatsapp-gateway-cli.sh inbound "<message>" [sender] [channel]
  whatsapp-gateway-cli.sh inbound-pdf "<pdf-url>" [message] [sender] [channel]
  whatsapp-gateway-cli.sh provider "<provider_message_id>" "<message>" [sender] [channel]
  whatsapp-gateway-cli.sh provider-pdf "<provider_message_id>" "<pdf-url>" [message] [sender] [channel]
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
  if [[ -n "$PORT_FORWARD_LOG" && -f "$PORT_FORWARD_LOG" ]]; then
    rm -f "$PORT_FORWARD_LOG"
  fi
}
trap cleanup EXIT

choose_local_port() {
  python3 - <<PY
import socket

preferred = int(${LOCAL_PORT})

def port_is_free(port: int) -> bool:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        sock.close()
    return True

if port_is_free(preferred):
    print(preferred)
else:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
    sock.close()
PY
}

wait_for_healthz() {
  python3 - <<PY >/dev/null 2>&1
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:${ACTIVE_LOCAL_PORT}/healthz", timeout=2) as response:
    payload = json.loads(response.read().decode("utf-8"))
    assert payload.get("status") == "ok"
PY
}

start_port_forward() {
  ACTIVE_LOCAL_PORT="$(choose_local_port)"
  PORT_FORWARD_LOG="$(mktemp /tmp/whatsapp-gateway-port-forward.XXXXXX.log)"
  kubectl -n "$NAMESPACE" port-forward "svc/$SERVICE" "${ACTIVE_LOCAL_PORT}:8097" >"$PORT_FORWARD_LOG" 2>&1 &
  PORT_FORWARD_PID=$!
  for _ in $(seq 1 40); do
    if ! kill -0 "$PORT_FORWARD_PID" >/dev/null 2>&1; then
      printf '[whatsapp-gateway-cli] port-forward exited early\n' >&2
      cat "$PORT_FORWARD_LOG" >&2 || true
      exit 1
    fi
    if wait_for_healthz; then
      return 0
    fi
    sleep 0.25
  done
  printf '[whatsapp-gateway-cli] port-forward did not become ready\n' >&2
  cat "$PORT_FORWARD_LOG" >&2 || true
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
with urllib.request.urlopen("http://127.0.0.1:${ACTIVE_LOCAL_PORT}/healthz", timeout=10) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  inbound)
    [[ $# -ge 1 ]] || usage
    message="$1"
    sender="${2:-$SENDER}"
    channel="${3:-$CHANNEL}"
    GW_SENDER="$sender" \
    GW_CHANNEL="$channel" \
    GW_MESSAGE="$message" \
    GW_PORT="$ACTIVE_LOCAL_PORT" \
    python3 - <<'PY'
import json
import os
import urllib.request
payload = {
    "sender": os.environ["GW_SENDER"],
    "channel": os.environ["GW_CHANNEL"],
    "message": os.environ["GW_MESSAGE"],
    "attachments": [],
}
req = urllib.request.Request(
    f"http://127.0.0.1:{os.environ['GW_PORT']}/webhooks/whatsapp/inbound",
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
    GW_SENDER="$sender" \
    GW_CHANNEL="$channel" \
    GW_MESSAGE="$message" \
    GW_PDF_URL="$pdf_url" \
    GW_PORT="$ACTIVE_LOCAL_PORT" \
    python3 - <<'PY'
import json
import os
import urllib.request
payload = {
    "sender": os.environ["GW_SENDER"],
    "channel": os.environ["GW_CHANNEL"],
    "message": os.environ["GW_MESSAGE"],
    "attachments": [{
        "url": os.environ["GW_PDF_URL"],
        "mime_type": "application/pdf",
        "filename": "attachment.pdf",
    }],
}
req = urllib.request.Request(
    f"http://127.0.0.1:{os.environ['GW_PORT']}/webhooks/whatsapp/inbound",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  provider)
    [[ $# -ge 2 ]] || usage
    provider_message_id="$1"
    message="$2"
    sender="${3:-$SENDER}"
    channel="${4:-$CHANNEL}"
    GW_PROVIDER_MESSAGE_ID="$provider_message_id" \
    GW_SENDER="$sender" \
    GW_CHANNEL="$channel" \
    GW_MESSAGE="$message" \
    GW_PORT="$ACTIVE_LOCAL_PORT" \
    python3 - <<'PY'
import json
import os
import urllib.request
payload = {
    "provider": "whatsapp",
    "provider_message_id": os.environ["GW_PROVIDER_MESSAGE_ID"],
    "sender": os.environ["GW_SENDER"],
    "channel": os.environ["GW_CHANNEL"],
    "text": os.environ["GW_MESSAGE"],
    "attachments": [],
}
req = urllib.request.Request(
    f"http://127.0.0.1:{os.environ['GW_PORT']}/webhooks/whatsapp/provider",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  provider-pdf)
    [[ $# -ge 2 ]] || usage
    provider_message_id="$1"
    pdf_url="$2"
    message="${3:-}"
    sender="${4:-$SENDER}"
    channel="${5:-$CHANNEL}"
    GW_PROVIDER_MESSAGE_ID="$provider_message_id" \
    GW_SENDER="$sender" \
    GW_CHANNEL="$channel" \
    GW_MESSAGE="$message" \
    GW_PDF_URL="$pdf_url" \
    GW_PORT="$ACTIVE_LOCAL_PORT" \
    python3 - <<'PY'
import json
import os
import urllib.request
payload = {
    "provider": "whatsapp",
    "provider_message_id": os.environ["GW_PROVIDER_MESSAGE_ID"],
    "sender": os.environ["GW_SENDER"],
    "channel": os.environ["GW_CHANNEL"],
    "text": os.environ["GW_MESSAGE"],
    "attachments": [{
        "url": os.environ["GW_PDF_URL"],
        "mime_type": "application/pdf",
        "filename": "attachment.pdf",
    }],
}
req = urllib.request.Request(
    f"http://127.0.0.1:{os.environ['GW_PORT']}/webhooks/whatsapp/provider",
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
with urllib.request.urlopen(f"http://127.0.0.1:${ACTIVE_LOCAL_PORT}/sessions/{channel}/{sender}", timeout=10) as response:
    print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
PY
    ;;
  *)
    usage
    ;;
esac
