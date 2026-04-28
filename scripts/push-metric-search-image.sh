#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${GLASSLAB_METRIC_SEARCH_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-metric-search:latest}"
REGISTRY_HOST="${GLASSLAB_METRIC_SEARCH_REGISTRY_HOST:-ghcr.io}"
REGISTRY_USERNAME="${GHCR_USERNAME:-${GITHUB_ACTOR:-OffensiveGeneric}}"
REGISTRY_TOKEN="${GHCR_TOKEN:-}"

usage() {
  cat <<'USAGE'
Usage: push-metric-search-image.sh [--image-ref <image>] [--username <user>]

Build the metric-search image locally and push it to GHCR.

Environment:
  GLASSLAB_METRIC_SEARCH_IMAGE_REF  Image reference with tag
  GHCR_TOKEN    GitHub token with package write access
  GHCR_USERNAME Registry username. Defaults to OffensiveGeneric.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-ref)
      IMAGE_REF="$2"
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
      printf '[push-metric-search-image] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REGISTRY_TOKEN" ]]; then
  printf '[push-metric-search-image] GHCR_TOKEN is required\n' >&2
  exit 1
fi

printf '[push-metric-search-image] logging into %s as %s\n' "$REGISTRY_HOST" "$REGISTRY_USERNAME"
printf '%s' "$REGISTRY_TOKEN" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USERNAME" --password-stdin >/dev/null

printf '[push-metric-search-image] building %s\n' "$IMAGE_REF"
cd "$ROOT_DIR/../../dml-project"
docker build -t "$IMAGE_REF" .

printf '[push-metric-search-image] pushing %s\n' "$IMAGE_REF"
docker push "$IMAGE_REF"

printf '[push-metric-search-image] done\n'
