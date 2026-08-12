#!/usr/bin/env bash
set -euo pipefail

# Remove only old local tags for the two CI-published control services. This
# never prunes containers, volumes, build cache, or unrelated images.
KEEP=3
APPLY=false
RETAIN_TAGS=()
REPOSITORIES=(
  'ghcr.io/ccny-glasslab/glasslab-workflow-api'
  'ghcr.io/ccny-glasslab/glasslab-research-orchestrator'
)

usage() {
  cat <<'USAGE'
Usage: prune-control-service-images.sh [--apply] [--keep N] [--retain-tag TAG]

Lists old local GHCR control-service image tags by default. --apply removes
only tags outside the retention window. Running-container image IDs and tags
named with --retain-tag are always preserved. This is a provisioner Docker
cache policy; worker-node image GC remains kubelet-managed.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true; shift ;;
    --keep) KEEP="${2:?missing value}"; shift 2 ;;
    --retain-tag) RETAIN_TAGS+=("${2:?missing value}"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { printf '%s\n' '--keep must be a positive integer' >&2; exit 2; }
command -v docker >/dev/null || { printf '%s\n' 'docker is required' >&2; exit 1; }

# `docker ps` does not expose an ImageID template field. Preserve the image
# references attached to running containers instead, which is exactly the tag
# this tool might otherwise remove.
mapfile -t RUNNING_REFS < <(docker ps --format '{{.Image}}' | sort -u)
is_running_ref() { local ref="$1"; local item; for item in "${RUNNING_REFS[@]}"; do [[ "$item" == "$ref" ]] && return 0; done; return 1; }
is_retained_tag() { local tag="$1"; local item; for item in "${RETAIN_TAGS[@]}"; do [[ "$item" == "$tag" ]] && return 0; done; return 1; }

removed=0
for repository in "${REPOSITORIES[@]}"; do
  # CreatedAt is formatted ISO-like by Docker and sorted newest first. <none>
  # tags are deliberately ignored: removing a dangling layer is not this tool's
  # job and can affect unrelated builds.
  mapfile -t rows < <(docker image ls "$repository" --format '{{.CreatedAt}}|{{.Tag}}|{{.ID}}' | sort -r)
  kept=0
  for row in "${rows[@]}"; do
    IFS='|' read -r _created tag image_id <<<"$row"
    [[ "$tag" == '<none>' ]] && continue
    ref="$repository:$tag"
    if is_running_ref "$ref" || is_retained_tag "$tag" || (( kept < KEEP )); then
      ((kept+=1))
      continue
    fi
    if [[ "$APPLY" == true ]]; then
      printf '[image-retention] removing old tag %s\n' "$ref"
      docker image rm "$ref"
    else
      printf '[image-retention] would remove %s (dry run)\n' "$ref"
    fi
    ((removed+=1))
  done
done
printf '[image-retention] %s %d old control-service tag(s)\n' "$([[ "$APPLY" == true ]] && echo removed || echo identified)" "$removed"
