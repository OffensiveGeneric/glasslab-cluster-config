#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  cat <<'USAGE' >&2
Usage: remote-44.sh <command ...>

Run a command on the canonical provisioner host through the Glasslab bastion.

Required environment:
- GLASSLAB_BASTION_PASS
- GLASSLAB_PROVISIONER_PASS

Optional environment:
- GLASSLAB_BASTION_HOST   default: glasslab.org
- GLASSLAB_BASTION_USER   default: glasslab
- GLASSLAB_PROVISIONER_HOST  default: 192.168.1.44
- GLASSLAB_PROVISIONER_USER  default: glasslab
USAGE
  exit 2
fi

: "${GLASSLAB_BASTION_PASS:?set GLASSLAB_BASTION_PASS}"
: "${GLASSLAB_PROVISIONER_PASS:?set GLASSLAB_PROVISIONER_PASS}"

BASTION_HOST="${GLASSLAB_BASTION_HOST:-glasslab.org}"
BASTION_USER="${GLASSLAB_BASTION_USER:-glasslab}"
PROVISIONER_HOST="${GLASSLAB_PROVISIONER_HOST:-192.168.1.44}"
PROVISIONER_USER="${GLASSLAB_PROVISIONER_USER:-glasslab}"

REMOTE_CMD="$(printf "%q " "$@")"

exec sshpass -p "$GLASSLAB_BASTION_PASS" \
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "${BASTION_USER}@${BASTION_HOST}" \
  "sshpass -p $(printf "%q" "$GLASSLAB_PROVISIONER_PASS") \
   ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
   ${PROVISIONER_USER}@${PROVISIONER_HOST} ${REMOTE_CMD}"
