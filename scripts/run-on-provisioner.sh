#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  cat <<'USAGE' >&2
Usage: run-on-provisioner.sh <command ...>

Run a command on the canonical Glasslab provisioner through the configured
key-based SSH path.

Optional environment:
- GLASSLAB_PROVISIONER_SSH_TARGET  default: glasslab-provisioner
USAGE
  exit 2
fi

SSH_TARGET="${GLASSLAB_PROVISIONER_SSH_TARGET:-glasslab-provisioner}"

exec ssh "$SSH_TARGET" -- "$@"
