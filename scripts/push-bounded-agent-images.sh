#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY_HOST="${GLASSLAB_AGENT_REGISTRY_HOST:-ghcr.io}"
REGISTRY_USERNAME="${GHCR_USERNAME:-${GITHUB_ACTOR:-OffensiveGeneric}}"
REGISTRY_TOKEN="${GHCR_TOKEN:-}"

INTAKE_IMAGE_REF="${GLASSLAB_INTAKE_AGENT_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-intake-agent:0.1.0}"
INTERPRETATION_IMAGE_REF="${GLASSLAB_INTERPRETATION_AGENT_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-interpretation-agent:0.1.0}"
ASSESSMENT_IMAGE_REF="${GLASSLAB_ASSESSMENT_AGENT_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-assessment-agent:0.1.0}"
DESIGN_IMAGE_REF="${GLASSLAB_DESIGN_AGENT_IMAGE_REF:-ghcr.io/offensivegeneric/glasslab-design-agent:0.1.0}"

usage() {
  cat <<'USAGE'
Usage: push-bounded-agent-images.sh

Build and push the bounded stage-agent images to GHCR.

Environment:
  GHCR_TOKEN    GitHub token with package write access
  GHCR_USERNAME Registry username. Defaults to OffensiveGeneric.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ -z "$REGISTRY_TOKEN" ]]; then
  printf '[push-bounded-agent-images] GHCR_TOKEN is required\n' >&2
  exit 1
fi

printf '[push-bounded-agent-images] logging into %s as %s\n' "$REGISTRY_HOST" "$REGISTRY_USERNAME"
printf '%s' "$REGISTRY_TOKEN" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USERNAME" --password-stdin >/dev/null

build_and_push() {
  local image_ref="$1"
  local dockerfile="$2"
  printf '[push-bounded-agent-images] building %s\n' "$image_ref"
  docker build -t "$image_ref" -f "$dockerfile" "$ROOT_DIR"
  printf '[push-bounded-agent-images] pushing %s\n' "$image_ref"
  docker push "$image_ref"
}

build_and_push "$INTAKE_IMAGE_REF" "$ROOT_DIR/services/intake-agent/Dockerfile"
build_and_push "$INTERPRETATION_IMAGE_REF" "$ROOT_DIR/services/interpretation-agent/Dockerfile"
build_and_push "$ASSESSMENT_IMAGE_REF" "$ROOT_DIR/services/assessment-agent/Dockerfile"
build_and_push "$DESIGN_IMAGE_REF" "$ROOT_DIR/services/design-agent/Dockerfile"

printf '[push-bounded-agent-images] done\n'
