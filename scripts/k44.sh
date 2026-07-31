#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

printf '%s\n' \
  'k44.sh is deprecated; use kube-on-provisioner.sh instead.' >&2

exec "$SCRIPT_DIR/kube-on-provisioner.sh" "$@"
