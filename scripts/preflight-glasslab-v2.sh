#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
KUBECTL="${KUBECTL:-kubectl}"
WORKFLOW_SERVICE_ACCOUNT="${GLASSLAB_WORKFLOW_API_SERVICE_ACCOUNT:-glasslab-workflow-api}"

usage() {
  cat <<'USAGE'
Usage: preflight-glasslab-v2.sh

Verify the prerequisites for durable Glasslab v2 operation and bounded job
submission. This does not create a workload or expose a service.
USAGE
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[preflight-glasslab-v2] missing command: %s\n' "$1" >&2
    exit 1
  }
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *) printf '[preflight-glasslab-v2] unknown argument: %s\n' "$1" >&2; usage >&2; exit 1 ;;
  esac
done

need_cmd "$KUBECTL"
need_cmd python3

printf '[preflight-glasslab-v2] namespace %s\n' "$NAMESPACE"
"$KUBECTL" get namespace "$NAMESPACE" >/dev/null

printf '[preflight-glasslab-v2] durable claims\n'
for claim in \
  glasslab-postgres-data \
  glasslab-minio-data \
  glasslab-nats-data \
  glasslab-shared-datasets \
  glasslab-shared-artifacts; do
  phase="$("$KUBECTL" -n "$NAMESPACE" get pvc "$claim" -o jsonpath='{.status.phase}')"
  if [[ "$phase" != "Bound" ]]; then
    printf '[preflight-glasslab-v2] PVC %s is %s, expected Bound\n' "$claim" "${phase:-missing}" >&2
    exit 1
  fi
done

secret_type="$("$KUBECTL" -n "$NAMESPACE" get secret glasslab-ghcr-pull -o jsonpath='{.type}')"
if [[ "$secret_type" != "kubernetes.io/dockerconfigjson" ]]; then
  printf '[preflight-glasslab-v2] glasslab-ghcr-pull must be a Docker registry secret\n' >&2
  exit 1
fi
printf '[preflight-glasslab-v2] GHCR pull secret present\n'

for verb in create get list watch; do
  allowed="$("$KUBECTL" auth can-i "$verb" jobs.batch \
    --as="system:serviceaccount:${NAMESPACE}:${WORKFLOW_SERVICE_ACCOUNT}" \
    -n "$NAMESPACE")"
  if [[ "$allowed" != "yes" ]]; then
    printf '[preflight-glasslab-v2] workflow API may not %s jobs.batch\n' "$verb" >&2
    exit 1
  fi
done
printf '[preflight-glasslab-v2] workflow API job-submission RBAC is sufficient\n'

"$KUBECTL" -n "$NAMESPACE" get deployments -o json | python3 -c '
import json
import re
import sys

deployments = json.load(sys.stdin).get("items", [])
errors = []
for deployment in deployments:
    name = deployment["metadata"]["name"]
    spec = deployment["spec"]["template"]["spec"]
    images = [container["image"] for container in spec.get("containers", [])]
    custom_images = [image for image in images if image.startswith("ghcr.io/")]
    for image in custom_images:
        if not re.fullmatch(r"ghcr\.io/ccny-glasslab/glasslab-[a-z0-9-]+:[0-9a-f]{40}", image):
            errors.append(
                f"{name} must use a ccny-glasslab full commit-SHA image tag, got {image}"
            )
    if custom_images and "glasslab-ghcr-pull" not in [item["name"] for item in spec.get("imagePullSecrets", [])]:
        errors.append(f"{name} has a GHCR image but does not reference glasslab-ghcr-pull")
if errors:
    print("[preflight-glasslab-v2] image distribution failures:", file=sys.stderr)
    print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
    raise SystemExit(1)
print("[preflight-glasslab-v2] active deployment image references are GHCR-ready")
'
