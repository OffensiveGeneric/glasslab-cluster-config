#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

printf '%s\n' \
  'remote-44.sh is deprecated; use run-on-provisioner.sh instead.' >&2

exec "$SCRIPT_DIR/run-on-provisioner.sh" "$@"
