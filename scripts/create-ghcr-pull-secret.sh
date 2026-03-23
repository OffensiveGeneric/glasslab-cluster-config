#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
SECRET_NAME="${GLASSLAB_GHCR_PULL_SECRET_NAME:-glasslab-ghcr-pull}"
REGISTRY_HOST="${GLASSLAB_WORKFLOW_API_REGISTRY_HOST:-ghcr.io}"
REGISTRY_USERNAME="${GHCR_USERNAME:-${GITHUB_ACTOR:-OffensiveGeneric}}"
REGISTRY_TOKEN="${GHCR_TOKEN:-}"

usage() {
  cat <<'USAGE'
Usage: create-ghcr-pull-secret.sh [--namespace <ns>] [--secret-name <name>] [--username <user>]

Create or refresh the private GHCR Docker registry secret used by Glasslab v2.

Environment:
  GHCR_TOKEN    GitHub token with package read access
  GHCR_USERNAME Registry username. Defaults to OffensiveGeneric.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --secret-name)
      SECRET_NAME="$2"
      shift 2
      ;;
    --username)
      REGISTRY_USERNAME="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[create-ghcr-pull-secret] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REGISTRY_TOKEN" ]]; then
  printf '[create-ghcr-pull-secret] GHCR_TOKEN is required\n' >&2
  exit 1
fi

printf '[create-ghcr-pull-secret] refreshing %s in namespace %s\n' "$SECRET_NAME" "$NAMESPACE"
"$KUBECTL" -n "$NAMESPACE" create secret docker-registry "$SECRET_NAME" \
  --docker-server="$REGISTRY_HOST" \
  --docker-username="$REGISTRY_USERNAME" \
  --docker-password="$REGISTRY_TOKEN" \
  --dry-run=client \
  -o yaml | "$KUBECTL" apply -f -

printf '[create-ghcr-pull-secret] done\n'
