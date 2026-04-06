#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${GLASSLAB_WHATSAPP_WEB_BRIDGE_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-whatsapp-web-bridge:0.1.0-local}"
NODE_HOST="${GLASSLAB_WHATSAPP_WEB_BRIDGE_NODE_HOST:-192.168.1.47}"
NODE_USER="${GLASSLAB_WHATSAPP_WEB_BRIDGE_NODE_USER:-clusteradmin}"
NODE_SSH_KEY="${GLASSLAB_WHATSAPP_WEB_BRIDGE_NODE_SSH_KEY:-/home/glasslab/.ssh/id_ed25519}"

cd "$ROOT_DIR"
sudo docker build -t "$IMAGE_REF" -f services/whatsapp-web-bridge/Dockerfile .
LOCAL_TAR="$(mktemp /tmp/glasslab-whatsapp-web-bridge-XXXXXX.tar)"
REMOTE_TAR="/tmp/$(basename "$LOCAL_TAR")"
cleanup() {
  rm -f "$LOCAL_TAR"
  ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "rm -f '$REMOTE_TAR'" >/dev/null 2>&1 || true
}
trap cleanup EXIT
sudo docker save -o "$LOCAL_TAR" "$IMAGE_REF"
sudo chown "$(id -u)":"$(id -g)" "$LOCAL_TAR"
scp -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "$LOCAL_TAR" "${NODE_USER}@${NODE_HOST}:${REMOTE_TAR}"
ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "sudo -n /usr/local/sbin/glasslab-import-k8s-image '$REMOTE_TAR' && sudo -n /usr/local/sbin/glasslab-has-k8s-image '$IMAGE_REF'"
