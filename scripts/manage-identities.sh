#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/manage-identities.sh check [ansible options]
       scripts/manage-identities.sh apply [ansible options]

Run this on the provisioner from its canonical cluster-config checkout.
Additional arguments are passed to ansible-playbook, for example:
  scripts/manage-identities.sh check --limit exo_macs
EOF
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

mode="$1"
shift

case "$mode" in
  check)
    mode_args=(--check --diff)
    ;;
  apply)
    mode_args=(--diff)
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root/ansible"

exec ansible-playbook \
  -i inventory/hosts.yml \
  playbooks/manage-lab-identities.yml \
  "${mode_args[@]}" \
  "$@"
