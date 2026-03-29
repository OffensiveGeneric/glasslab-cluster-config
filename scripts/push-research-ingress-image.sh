#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_REF="${GLASSLAB_RESEARCH_INGRESS_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-research-ingress:0.1.0}"
REGISTRY_HOST="${GLASSLAB_RESEARCH_INGRESS_REGISTRY_HOST:-ghcr.io}"
REGISTRY_USERNAME="${GHCR_USERNAME:-${GITHUB_ACTOR:-OffensiveGeneric}}"
REGISTRY_TOKEN="${GHCR_TOKEN:-}"

usage() {
  cat <<'USAGE'
Usage: push-research-ingress-image.sh [--image-ref <image>] [--username <user>]

Build the research-ingress image locally and push it to GHCR.
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
      printf '[push-research-ingress-image] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REGISTRY_TOKEN" ]]; then
  printf '[push-research-ingress-image] GHCR_TOKEN is required\n' >&2
  exit 1
fi

printf '[push-research-ingress-image] logging into %s as %s\n' "$REGISTRY_HOST" "$REGISTRY_USERNAME"
printf '%s' "$REGISTRY_TOKEN" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USERNAME" --password-stdin >/dev/null

printf '[push-research-ingress-image] building %s\n' "$IMAGE_REF"
docker build \
  -t "$IMAGE_REF" \
  -f "$ROOT_DIR/services/research-ingress/Dockerfile" \
  "$ROOT_DIR"

printf '[push-research-ingress-image] pushing %s\n' "$IMAGE_REF"
docker push "$IMAGE_REF"

printf '[push-research-ingress-image] done\n'
