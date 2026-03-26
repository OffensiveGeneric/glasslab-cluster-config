#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -eq 0 ]]; then
  cat <<'USAGE' >&2
Usage: k44.sh <kubectl args...>

Examples:
  k44.sh get pods -n glasslab-v2
  k44.sh -n glasslab-v2 logs deploy/glasslab-openclaw --tail=100
USAGE
  exit 2
fi

exec "$SCRIPT_DIR/remote-44.sh" kubectl "$@"
