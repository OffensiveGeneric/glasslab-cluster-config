#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG_PATH="${GLASSLAB_PROVISIONER_KUBECONFIG:-/home/glasslab/.kube/config}"

if [[ $# -eq 0 ]]; then
  cat <<'USAGE' >&2
Usage: kube-on-provisioner.sh <kubectl args...>

Examples:
  kube-on-provisioner.sh get pods -n glasslab-v2
  kube-on-provisioner.sh -n glasslab-v2 logs deploy/glasslab-workflow-api --tail=100
USAGE
  exit 2
fi

exec "$SCRIPT_DIR/run-on-provisioner.sh" \
  sudo -n env "KUBECONFIG=$KUBECONFIG_PATH" kubectl "$@"
