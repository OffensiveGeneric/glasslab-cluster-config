#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat <<'USAGE' >&2
Usage:
  whatsapp-gateway-remote.sh inbound "<message>" [sender] [channel]
  whatsapp-gateway-remote.sh inbound-pdf "<pdf-url>" [message] [sender] [channel]
  whatsapp-gateway-remote.sh provider "<provider_message_id>" "<message>" [sender] [channel]
  whatsapp-gateway-remote.sh provider-pdf "<provider_message_id>" "<pdf-url>" [message] [sender] [channel]
  whatsapp-gateway-remote.sh session [sender] [channel]
  whatsapp-gateway-remote.sh healthz
USAGE
  exit 2
fi

REMOTE_SCRIPT="/home/glasslab/cluster-config/scripts/whatsapp-gateway-cli.sh"
exec ssh glasslab-44 bash "$REMOTE_SCRIPT" "$@"
