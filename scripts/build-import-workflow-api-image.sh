#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${GLASSLAB_WORKFLOW_API_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.0}"
NODE_HOST="${GLASSLAB_WORKFLOW_API_NODE_HOST:-192.168.1.50}"
NODE_USER="${GLASSLAB_WORKFLOW_API_NODE_USER:-clusteradmin}"
NODE_SSH_KEY="${GLASSLAB_WORKFLOW_API_NODE_SSH_KEY:-/home/glasslab/.ssh/id_ed25519}"
NODE_SUDO_PASSWORD="${NODE_SUDO_PASSWORD:-}"
USE_PASSWORDLESS_SUDO=false
LOCAL_TAR=""
REMOTE_TAR=""

usage() {
  cat <<'USAGE'
Usage: build-import-workflow-api-image.sh [--node-host <host>] [--image-ref <image>]

Build the local workflow-api image on the provisioner with sudo docker and import it into node03 containerd.
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
    printf '[build-import-workflow-api-image] missing command: %s\n' "$1" >&2
    exit 1
  }
}

prompt_node_password() {
  if [[ -n "$NODE_SUDO_PASSWORD" ]]; then
    return
  fi
  read -r -s -p "sudo password for ${NODE_USER}@${NODE_HOST}: " NODE_SUDO_PASSWORD
  printf '\n' >&2
  [[ -n "$NODE_SUDO_PASSWORD" ]] || {
    printf '[build-import-workflow-api-image] node sudo password is required\n' >&2
    exit 1
  }
}

detect_node_sudo_mode() {
  if ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" "sudo -n true" >/dev/null 2>&1; then
    USE_PASSWORDLESS_SUDO=true
    printf '[build-import-workflow-api-image] using passwordless sudo on %s\n' "$NODE_HOST"
    return
  fi

  prompt_node_password
}

run_remote_root() {
  local remote_cmd="$1"

  if [[ "$USE_PASSWORDLESS_SUDO" == true ]]; then
    ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
      "sudo -n bash -lc $(printf '%q' "$remote_cmd")"
    return
  fi

  local password_b64
  password_b64="$(printf '%s' "$NODE_SUDO_PASSWORD" | base64 -w0)"
  ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
    "PASSWORD_B64='$password_b64' bash -lc 'printf %s \"\$PASSWORD_B64\" | base64 -d | sudo -S bash -lc $(printf '%q' "$remote_cmd")'"
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
      printf '[build-import-workflow-api-image] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd sudo
need_cmd docker
need_cmd ssh
need_cmd scp
need_cmd base64

[[ -f "$NODE_SSH_KEY" ]] || {
  printf '[build-import-workflow-api-image] ssh key not found: %s\n' "$NODE_SSH_KEY" >&2
  exit 1
}

printf '[build-import-workflow-api-image] building %s\n' "$IMAGE_REF"
cd "$ROOT_DIR"
sudo docker build -t "$IMAGE_REF" -f services/workflow-api/Dockerfile .

LOCAL_TAR="$(mktemp /tmp/glasslab-workflow-api-XXXXXX.tar)"
REMOTE_TAR="/tmp/$(basename "$LOCAL_TAR")"

printf '[build-import-workflow-api-image] saving image archive to %s\n' "$LOCAL_TAR"
sudo docker save -o "$LOCAL_TAR" "$IMAGE_REF"

printf '[build-import-workflow-api-image] copying archive to %s:%s\n' "$NODE_HOST" "$REMOTE_TAR"
scp -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "$LOCAL_TAR" "${NODE_USER}@${NODE_HOST}:${REMOTE_TAR}"

detect_node_sudo_mode

printf '[build-import-workflow-api-image] importing image into %s\n' "$NODE_HOST"
run_remote_root "ctr -n k8s.io images import \"$REMOTE_TAR\""

printf '[build-import-workflow-api-image] verifying image on %s\n' "$NODE_HOST"
run_remote_root "ctr -n k8s.io images ls | grep -F \"$IMAGE_REF\""
