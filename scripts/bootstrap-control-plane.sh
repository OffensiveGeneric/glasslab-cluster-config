#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/ansible"
exec ansible-playbook playbooks/bootstrap-control-plane.yml --limit control_plane -K
