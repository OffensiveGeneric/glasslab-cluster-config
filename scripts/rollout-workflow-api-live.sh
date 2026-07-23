#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
DEPLOYMENT="${GLASSLAB_WORKFLOW_API_DEPLOYMENT:-glasslab-workflow-api}"
CONTAINER="${GLASSLAB_WORKFLOW_API_CONTAINER:-workflow-api}"
IMAGE_REPO="${GLASSLAB_WORKFLOW_API_IMAGE_REPO:-ghcr.io/offensivegeneric/glasslab-workflow-api}"
DOCKER_CONFIG_DIR="${GLASSLAB_DOCKER_CONFIG:-${DOCKER_CONFIG:-$HOME/.docker}}"
SUDO="${SUDO:-sudo}"
SYNC=false
SKIP_PUSH=false
SKIP_SMOKE=false

usage() {
  cat <<'USAGE'
Usage: rollout-workflow-api-live.sh [--sync] [--skip-push] [--skip-smoke]

Build, push, and roll out the workflow-api image from the canonical .44
checkout. The image tag is the current short git SHA.

Options:
  --sync        Fetch origin/main and hard-sync this clean checkout first.
  --skip-push   Build locally but do not push the image.
  --skip-smoke  Do not run scripts/smoke-test-v2.sh after rollout.

Environment:
  GLASSLAB_V2_NAMESPACE              Kubernetes namespace. Default: glasslab-v2
  GLASSLAB_WORKFLOW_API_IMAGE_REPO   Image repository. Default: GHCR workflow-api
  GLASSLAB_DOCKER_CONFIG             Docker config dir used under sudo.
  SUDO                               Sudo command. Default: sudo
USAGE
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[rollout-workflow-api-live] missing command: %s\n' "$1" >&2
    exit 1
  }
}

docker_sudo() {
  "$SUDO" -E env DOCKER_CONFIG="$DOCKER_CONFIG_DIR" docker "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sync)
      SYNC=true
      shift
      ;;
    --skip-push)
      SKIP_PUSH=true
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[rollout-workflow-api-live] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd git
need_cmd kubectl
need_cmd docker

cd "$ROOT_DIR"

if [[ "$SYNC" == true ]]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    printf '[rollout-workflow-api-live] refusing to sync over a dirty checkout\n' >&2
    git status --short >&2
    exit 1
  fi
  printf '[rollout-workflow-api-live] syncing canonical checkout to origin/main\n'
  git fetch origin main
  git checkout main
  git reset --hard origin/main
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  printf '[rollout-workflow-api-live] refusing to roll out from a dirty checkout\n' >&2
  git status --short >&2
  exit 1
fi

SHA="$(git rev-parse --short HEAD)"
IMAGE_REF="${IMAGE_REPO}:${SHA}"
LOCAL_SECRET="kubeadm/glasslab-v2/secrets/15-workflow-api.local.yaml"

if [[ ! -f "$LOCAL_SECRET" ]]; then
  printf '[rollout-workflow-api-live] missing required local secret: %s\n' "$LOCAL_SECRET" >&2
  exit 1
fi

printf '[rollout-workflow-api-live] building %s\n' "$IMAGE_REF"
docker_sudo build \
  --build-arg "GLASSLAB_GIT_SHA=$SHA" \
  --build-arg "GLASSLAB_BUILD_SOURCE=git:$SHA" \
  -t "$IMAGE_REF" \
  -f services/workflow-api/Dockerfile \
  .

if [[ "$SKIP_PUSH" != true ]]; then
  printf '[rollout-workflow-api-live] pushing %s\n' "$IMAGE_REF"
  docker_sudo push "$IMAGE_REF"
fi

printf '[rollout-workflow-api-live] applying safe workflow-api prerequisites\n'
kubectl apply -n "$NAMESPACE" -f kubeadm/glasslab-v2/config/10-workflow-api-configmap.yaml
kubectl apply -n "$NAMESPACE" -f kubeadm/glasslab-v2/workflow-api/10-rbac.yaml
kubectl apply -n "$NAMESPACE" -f kubeadm/glasslab-v2/workflow-api/30-service.yaml
kubectl apply -n "$NAMESPACE" -f "$LOCAL_SECRET"

printf '[rollout-workflow-api-live] applying deployment and pinning image to %s\n' "$IMAGE_REF"
kubectl apply -n "$NAMESPACE" -f kubeadm/glasslab-v2/workflow-api/20-deployment.yaml
kubectl set image -n "$NAMESPACE" "deployment/$DEPLOYMENT" "$CONTAINER=$IMAGE_REF"
kubectl -n "$NAMESPACE" rollout status "deployment/$DEPLOYMENT" --timeout=300s

printf '[rollout-workflow-api-live] live image: '
kubectl -n "$NAMESPACE" get deploy "$DEPLOYMENT" -o jsonpath='{.spec.template.spec.containers[0].image}'
printf '\n'

if [[ "$SKIP_SMOKE" != true ]]; then
  "$ROOT_DIR/scripts/smoke-test-v2.sh"
fi

printf '[rollout-workflow-api-live] done\n'
