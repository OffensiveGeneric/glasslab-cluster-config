#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat <<'USAGE' >&2
Usage:
  research-ingress-remote.sh dispatch "<message>" [sender] [channel]
  research-ingress-remote.sh healthz
USAGE
  exit 2
fi

REMOTE_SCRIPT="/home/glasslab/cluster-config/scripts/research-ingress-cli.sh"

remote_cmd="$(printf '%q ' "$REMOTE_SCRIPT" "$@")"
exec ssh glasslab-44 "bash -lc $(
  printf '%q' "$remote_cmd"
)"
