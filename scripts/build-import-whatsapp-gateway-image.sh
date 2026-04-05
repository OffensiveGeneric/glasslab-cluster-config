#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${GLASSLAB_WHATSAPP_GATEWAY_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-whatsapp-gateway:0.1.1-local}"
NODE_HOST="${GLASSLAB_WHATSAPP_GATEWAY_NODE_HOST:-192.168.1.47}"
NODE_USER="${GLASSLAB_WHATSAPP_GATEWAY_NODE_USER:-clusteradmin}"
NODE_SSH_KEY="${GLASSLAB_WHATSAPP_GATEWAY_NODE_SSH_KEY:-/home/glasslab/.ssh/id_ed25519}"
GIT_SHA="${GLASSLAB_GIT_SHA:-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"
BUILD_SOURCE="${GLASSLAB_BUILD_SOURCE:-git:${GIT_SHA}}"
USE_PASSWORDLESS_SUDO=false
USE_WRAPPER_SUDO=false
LOCAL_TAR=""
REMOTE_TAR=""

usage() {
  cat <<'USAGE'
Usage: build-import-whatsapp-gateway-image.sh [--node-host <host>] [--image-ref <image>]

Build the local whatsapp-gateway image on the provisioner and import it into the
target node containerd.
USAGE
}

cleanup() {
  if [[ -n "$LOCAL_TAR" && -f "$LOCAL_TAR" ]]; then
    rm -f "$LOCAL_TAR"
  fi
  if [[ -n "$REMOTE_TAR" ]]; then
    ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "rm -f '$REMOTE_TAR'" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[build-import-whatsapp-gateway-image] missing command: %s\n' "$1" >&2
    exit 1
  }
}

fail_node_sudo_mode() {
  printf '[build-import-whatsapp-gateway-image] %s\n' "$1" >&2
  printf '[build-import-whatsapp-gateway-image] enable reviewed wrapper sudo or passwordless sudo on %s\n' "$NODE_HOST" >&2
  exit 1
}

detect_node_sudo_mode() {
  if ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "sudo -n true" >/dev/null 2>&1; then
    USE_PASSWORDLESS_SUDO=true
    printf '[build-import-whatsapp-gateway-image] using passwordless sudo on %s\n' "$NODE_HOST"
    return
  fi

  if ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
    "sudo -n /usr/local/sbin/glasslab-import-k8s-image --help >/dev/null 2>&1 && sudo -n /usr/local/sbin/glasslab-has-k8s-image --help >/dev/null 2>&1"; then
    USE_WRAPPER_SUDO=true
    printf '[build-import-whatsapp-gateway-image] using wrapper-based passwordless sudo on %s\n' "$NODE_HOST"
    return
  fi

  fail_node_sudo_mode "node does not expose passwordless sudo or the reviewed image-import wrappers"
}

run_remote_root() {
  local remote_cmd="$1"

  if [[ "$USE_PASSWORDLESS_SUDO" == true ]]; then
    ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
      "sudo -n bash -lc $(printf '%q' "$remote_cmd")"
    return
  fi

  fail_node_sudo_mode "run_remote_root called without passwordless sudo"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node-host)
      NODE_HOST="$2"
      shift 2
      ;;
    --image-ref)
      IMAGE_REF="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[build-import-whatsapp-gateway-image] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd sudo
need_cmd docker
need_cmd ssh
need_cmd scp

[[ -f "$NODE_SSH_KEY" ]] || {
  printf '[build-import-whatsapp-gateway-image] ssh key not found: %s\n' "$NODE_SSH_KEY" >&2
  exit 1
}

printf '[build-import-whatsapp-gateway-image] building %s from %s (%s)\n' "$IMAGE_REF" "$BUILD_SOURCE" "$GIT_SHA"
cd "$ROOT_DIR"
sudo docker build \
  --build-arg "GLASSLAB_GIT_SHA=$GIT_SHA" \
  --build-arg "GLASSLAB_BUILD_SOURCE=$BUILD_SOURCE" \
  -t "$IMAGE_REF" \
  -f services/whatsapp-gateway/Dockerfile \
  .

LOCAL_TAR="$(mktemp /tmp/glasslab-whatsapp-gateway-XXXXXX.tar)"
REMOTE_TAR="/tmp/$(basename "$LOCAL_TAR")"

printf '[build-import-whatsapp-gateway-image] saving image archive to %s\n' "$LOCAL_TAR"
sudo docker save -o "$LOCAL_TAR" "$IMAGE_REF"
sudo chown "$(id -u)":"$(id -g)" "$LOCAL_TAR"

printf '[build-import-whatsapp-gateway-image] copying archive to %s:%s\n' "$NODE_HOST" "$REMOTE_TAR"
scp -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "$LOCAL_TAR" "${NODE_USER}@${NODE_HOST}:${REMOTE_TAR}"

detect_node_sudo_mode

printf '[build-import-whatsapp-gateway-image] importing image into %s\n' "$NODE_HOST"
if [[ "$USE_WRAPPER_SUDO" == true ]]; then
  ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
    "sudo -n /usr/local/sbin/glasslab-import-k8s-image \"$REMOTE_TAR\""
else
  run_remote_root "ctr -n k8s.io images import \"$REMOTE_TAR\""
fi

printf '[build-import-whatsapp-gateway-image] verifying image on %s\n' "$NODE_HOST"
if [[ "$USE_WRAPPER_SUDO" == true ]]; then
  ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
    "sudo -n /usr/local/sbin/glasslab-has-k8s-image \"$IMAGE_REF\""
else
  run_remote_root "ctr -n k8s.io images ls | grep -F \"$IMAGE_REF\""
fi
