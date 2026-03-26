#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
SERVICE_ACCOUNT="${GLASSLAB_WORKFLOW_API_SERVICE_ACCOUNT:-glasslab-workflow-api}"
DATASET_PVC="${GLASSLAB_WORKFLOW_API_DATASET_PVC_NAME:-glasslab-shared-datasets}"
ARTIFACTS_PVC="${GLASSLAB_WORKFLOW_API_ARTIFACTS_PVC_NAME:-glasslab-shared-artifacts}"
PULL_SECRET="${GLASSLAB_WORKFLOW_API_IMAGE_PULL_SECRET_NAME:-glasslab-ghcr-pull}"

status=0

check_exists() {
  local kind="$1"
  local name="$2"
  if "$KUBECTL" -n "$NAMESPACE" get "$kind" "$name" >/dev/null 2>&1; then
    printf '[ok] %s/%s exists in %s\n' "$kind" "$name" "$NAMESPACE"
  else
    printf '[missing] %s/%s is not present in %s\n' "$kind" "$name" "$NAMESPACE" >&2
    status=1
  fi
}

check_can_i() {
  local verb="$1"
  local resource="$2"
  if "$KUBECTL" auth can-i --as="system:serviceaccount:${NAMESPACE}:${SERVICE_ACCOUNT}" -n "$NAMESPACE" "$verb" "$resource" >/dev/null 2>&1; then
    printf '[ok] serviceaccount/%s can %s %s\n' "$SERVICE_ACCOUNT" "$verb" "$resource"
  else
    printf '[missing-rbac] serviceaccount/%s cannot %s %s\n' "$SERVICE_ACCOUNT" "$verb" "$resource" >&2
    status=1
  fi
}

check_exists pvc "$DATASET_PVC"
check_exists pvc "$ARTIFACTS_PVC"
check_exists secret "$PULL_SECRET"

check_can_i get persistentvolumeclaims
check_can_i get secrets
check_can_i list nodes
check_can_i list pods

exit "$status"
