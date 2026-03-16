#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${GLASSLAB_WORKFLOW_API_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.0}"
NODE_HOST="${GLASSLAB_WORKFLOW_API_NODE_HOST:-192.168.1.50}"
NODE_USER="${GLASSLAB_WORKFLOW_API_NODE_USER:-clusteradmin}"
NODE_SSH_KEY="${GLASSLAB_WORKFLOW_API_NODE_SSH_KEY:-/home/glasslab/.ssh/id_ed25519}"
NODE_SUDO_PASSWORD="${NODE_SUDO_PASSWORD:-}"

usage() {
  cat <<'USAGE'
Usage: build-import-workflow-api-image.sh [--node-host <host>] [--image-ref <image>]

Build the local workflow-api image on the provisioner with sudo docker and import it into node03 containerd.
USAGE
}

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
need_cmd base64

[[ -f "$NODE_SSH_KEY" ]] || {
  printf '[build-import-workflow-api-image] ssh key not found: %s\n' "$NODE_SSH_KEY" >&2
  exit 1
}

printf '[build-import-workflow-api-image] building %s\n' "$IMAGE_REF"
cd "$ROOT_DIR"
sudo docker build -t "$IMAGE_REF" -f services/workflow-api/Dockerfile .

prompt_node_password
PASSWORD_B64="$(printf '%s' "$NODE_SUDO_PASSWORD" | base64 -w0)"

printf '[build-import-workflow-api-image] priming sudo on %s\n' "$NODE_HOST"
ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
  "PASSWORD_B64='$PASSWORD_B64' bash -lc 'printf %s \"\$PASSWORD_B64\" | base64 -d | sudo -S -v >/dev/null'"

printf '[build-import-workflow-api-image] importing image into %s\n' "$NODE_HOST"
sudo docker save "$IMAGE_REF" | ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
  "sudo ctr -n k8s.io images import -"

printf '[build-import-workflow-api-image] verifying image on %s\n' "$NODE_HOST"
ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${NODE_HOST}" \
  "sudo ctr -n k8s.io images ls | grep -F \"$IMAGE_REF\""
