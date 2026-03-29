#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  cat <<'USAGE' >&2
Usage:
  research-session-remote.sh start "goal statement"
  research-session-remote.sh new "goal statement"
  research-session-remote.sh context
  research-session-remote.sh next-paper
  research-session-remote.sh note "text"
  research-session-remote.sh op

Run the deterministic research-session CLI on the canonical .44 provisioner.
USAGE
  exit 2
fi

REMOTE_SCRIPT="/home/glasslab/cluster-config/scripts/research-session-cli.sh"

exec ssh glasslab-44 "$REMOTE_SCRIPT" "$@"
