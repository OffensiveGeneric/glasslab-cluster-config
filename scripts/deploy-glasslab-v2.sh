#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_ROOT="$ROOT_DIR/kubeadm/glasslab-v2"
KUBECTL="${KUBECTL:-kubectl}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[deploy-glasslab-v2] missing command: %s\n' "$1" >&2
    exit 1
  }
}

apply_yaml_dir() {
  local dir="$1"
  if ! find "$dir" -maxdepth 1 -type f -name '*.yaml' | grep -q .; then
    printf '[deploy-glasslab-v2] skipping %s (no YAML manifests yet)\n' "$dir"
    return
  fi

  while IFS= read -r file; do
    printf '[deploy-glasslab-v2] applying %s\n' "$file"
    "$KUBECTL" apply -f "$file"
  done < <(find "$dir" -maxdepth 1 -type f -name '*.yaml' | sort)
}

need_cmd "$KUBECTL"

printf '[deploy-glasslab-v2] validating workflow registry definitions\n'
"$ROOT_DIR/scripts/seed-registry.sh"

apply_yaml_dir "$MANIFEST_ROOT/namespaces"
apply_yaml_dir "$MANIFEST_ROOT/config"
apply_yaml_dir "$MANIFEST_ROOT/postgres"
apply_yaml_dir "$MANIFEST_ROOT/nats"
apply_yaml_dir "$MANIFEST_ROOT/minio"
apply_yaml_dir "$MANIFEST_ROOT/workflow-api"

printf '[deploy-glasslab-v2] exporting repo-managed OpenClaw config\n'
"$ROOT_DIR/scripts/export-openclaw-config.sh"
apply_yaml_dir "$MANIFEST_ROOT/openclaw"
