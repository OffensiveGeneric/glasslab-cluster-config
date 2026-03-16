#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_ROOT="$ROOT_DIR/kubeadm/glasslab-v2"
KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
INCLUDE_OPENCLAW=false

usage() {
  cat <<'USAGE'
Usage: deploy-glasslab-v2.sh [--include-openclaw]

Deploy the core Glasslab v2 services by default:
- namespace
- local secrets if present
- config
- Postgres
- NATS
- MinIO
- workflow-api

OpenClaw is skipped unless --include-openclaw is supplied.
Example manifests ending in .example.yaml are never applied.
USAGE
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[deploy-glasslab-v2] missing command: %s\n' "$1" >&2
    exit 1
  }
}

require_k8s_object() {
  local namespace="$1"
  local kind="$2"
  local name="$3"
  if ! "$KUBECTL" -n "$namespace" get "$kind" "$name" >/dev/null 2>&1; then
    printf '[deploy-glasslab-v2] required %s/%s not found in namespace %s\n' "$kind" "$name" "$namespace" >&2
    exit 1
  fi
}

apply_yaml_dir() {
  local dir="$1"
  if ! find "$dir" -maxdepth 1 -type f -name '*.yaml' ! -name '*.example.yaml' | grep -q .; then
    printf '[deploy-glasslab-v2] skipping %s (no deployable YAML manifests yet)\n' "$dir"
    return
  fi

  while IFS= read -r file; do
    printf '[deploy-glasslab-v2] applying %s\n' "$file"
    "$KUBECTL" apply -f "$file"
  done < <(find "$dir" -maxdepth 1 -type f -name '*.yaml' ! -name '*.example.yaml' | sort)
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-openclaw)
      INCLUDE_OPENCLAW=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[deploy-glasslab-v2] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd "$KUBECTL"

printf '[deploy-glasslab-v2] validating workflow registry definitions\n'
"$ROOT_DIR/scripts/seed-registry.sh"

apply_yaml_dir "$MANIFEST_ROOT/namespaces"
apply_yaml_dir "$MANIFEST_ROOT/secrets"
apply_yaml_dir "$MANIFEST_ROOT/config"
apply_yaml_dir "$MANIFEST_ROOT/postgres"
apply_yaml_dir "$MANIFEST_ROOT/nats"
apply_yaml_dir "$MANIFEST_ROOT/minio"
apply_yaml_dir "$MANIFEST_ROOT/workflow-api"

if [[ "$INCLUDE_OPENCLAW" == true ]]; then
  if [[ ! -f "$MANIFEST_ROOT/secrets/30-openclaw.local.yaml" ]]; then
    printf '[deploy-glasslab-v2] missing local OpenClaw secret manifest: %s\n' "$MANIFEST_ROOT/secrets/30-openclaw.local.yaml" >&2
    exit 1
  fi

  require_k8s_object "$NAMESPACE" service glasslab-workflow-api
  require_k8s_object glasslab-agents service vllm

  printf '[deploy-glasslab-v2] exporting repo-managed OpenClaw config\n'
  "$ROOT_DIR/scripts/export-openclaw-config.sh"
  apply_yaml_dir "$MANIFEST_ROOT/openclaw"
else
  printf '[deploy-glasslab-v2] skipping OpenClaw (core-only deploy)\n'
fi
