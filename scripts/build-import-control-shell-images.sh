#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INGRESS_IMAGE="${GLASSLAB_RESEARCH_INGRESS_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-research-ingress:0.1.1}"
ROUTER_IMAGE="${GLASSLAB_RESEARCH_COMMAND_ROUTER_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-research-command-router:0.1.8-local}"
GATEWAY_IMAGE="${GLASSLAB_WHATSAPP_GATEWAY_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-whatsapp-gateway:0.1.1-local}"
INGRESS_NODE="${GLASSLAB_RESEARCH_INGRESS_NODE_HOST:-192.168.1.11}"
ROUTER_NODE="${GLASSLAB_RESEARCH_COMMAND_ROUTER_NODE_HOST:-192.168.1.47}"
GATEWAY_NODE="${GLASSLAB_WHATSAPP_GATEWAY_NODE_HOST:-192.168.1.47}"
NODE_USER="${GLASSLAB_CONTROL_SHELL_NODE_USER:-clusteradmin}"
NODE_SSH_KEY="${GLASSLAB_CONTROL_SHELL_NODE_SSH_KEY:-/home/glasslab/.ssh/id_ed25519}"
SUDO_PASSWORD="${GLASSLAB_SUDO_PASSWORD:-}"

usage() {
  cat <<'USAGE'
Usage: build-import-control-shell-images.sh

Build the research-ingress, research-command-router, and whatsapp-gateway
images on the provisioner and import them into the worker nodes that currently
host those workloads.

Required environment:
  GLASSLAB_SUDO_PASSWORD

Optional environment:
  GLASSLAB_RESEARCH_INGRESS_IMAGE_REF
  GLASSLAB_RESEARCH_COMMAND_ROUTER_IMAGE_REF
  GLASSLAB_WHATSAPP_GATEWAY_IMAGE_REF
  GLASSLAB_RESEARCH_INGRESS_NODE_HOST
  GLASSLAB_RESEARCH_COMMAND_ROUTER_NODE_HOST
  GLASSLAB_WHATSAPP_GATEWAY_NODE_HOST
  GLASSLAB_CONTROL_SHELL_NODE_USER
  GLASSLAB_CONTROL_SHELL_NODE_SSH_KEY
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[build-import-control-shell-images] missing command: %s\n' "$1" >&2
    exit 1
  }
}

need_cmd sudo
need_cmd docker
need_cmd ssh
need_cmd scp

if [[ -z "$SUDO_PASSWORD" ]]; then
  printf '[build-import-control-shell-images] GLASSLAB_SUDO_PASSWORD is required\n' >&2
  exit 1
fi

if [[ ! -f "$NODE_SSH_KEY" ]]; then
  printf '[build-import-control-shell-images] missing node ssh key: %s\n' "$NODE_SSH_KEY" >&2
  exit 1
fi

run_sudo() {
  printf '%s\n' "$SUDO_PASSWORD" | sudo -S "$@"
}

build_import() {
  local image_ref="$1"
  local dockerfile="$2"
  local node_host="$3"
  local tar_path="$4"

  printf '[build-import-control-shell-images] building %s\n' "$image_ref"
  run_sudo docker build -t "$image_ref" -f "$dockerfile" "$ROOT_DIR"

  printf '[build-import-control-shell-images] saving %s to %s\n' "$image_ref" "$tar_path"
  run_sudo docker save -o "$tar_path" "$image_ref"
  run_sudo chown "$(id -u)":"$(id -g)" "$tar_path"

  printf '[build-import-control-shell-images] copying %s to %s\n' "$image_ref" "$node_host"
  scp -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "$tar_path" "${NODE_USER}@${node_host}:${tar_path}" >/dev/null
  ssh -i "$NODE_SSH_KEY" -o StrictHostKeyChecking=accept-new "${NODE_USER}@${node_host}" \
    "sudo -n /usr/local/sbin/glasslab-import-k8s-image '$tar_path' >/dev/null && rm -f '$tar_path'"

  rm -f "$tar_path"
}

cd "$ROOT_DIR"

build_import "$INGRESS_IMAGE" services/research-ingress/Dockerfile "$INGRESS_NODE" /tmp/research-ingress-rollout.tar
build_import "$ROUTER_IMAGE" services/research-command-router/Dockerfile "$ROUTER_NODE" /tmp/research-command-router-rollout.tar
build_import "$GATEWAY_IMAGE" services/whatsapp-gateway/Dockerfile "$GATEWAY_NODE" /tmp/whatsapp-gateway-rollout.tar

printf '[build-import-control-shell-images] restarting deployments\n'
kubectl -n glasslab-v2 rollout restart deploy/glasslab-research-ingress deploy/glasslab-research-command-router deploy/glasslab-whatsapp-gateway

printf '[build-import-control-shell-images] waiting for rollouts\n'
kubectl -n glasslab-v2 rollout status deploy/glasslab-research-ingress --timeout=180s
kubectl -n glasslab-v2 rollout status deploy/glasslab-research-command-router --timeout=180s
kubectl -n glasslab-v2 rollout status deploy/glasslab-whatsapp-gateway --timeout=180s

printf '[build-import-control-shell-images] done\n'
