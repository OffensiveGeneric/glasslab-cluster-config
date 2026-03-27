#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
DEPLOYMENT="${GLASSLAB_WORKFLOW_API_DEPLOYMENT:-glasslab-workflow-api}"
LOCAL_PORT="${GLASSLAB_WORKFLOW_API_LOCAL_PORT:-18080}"

image_ref="$(ssh glasslab-44 "kubectl -n '$NAMESPACE' get deploy '$DEPLOYMENT' -o jsonpath='{.spec.template.spec.containers[0].image}'")"
pod_name="$(ssh glasslab-44 "kubectl -n '$NAMESPACE' get pods -l app.kubernetes.io/name='$DEPLOYMENT' -o jsonpath='{.items[0].metadata.name}'")"

healthz_json="$(ssh glasslab-44 "kubectl -n '$NAMESPACE' port-forward svc/$DEPLOYMENT '$LOCAL_PORT':8080 >/tmp/workflow-api-provenance-pf.log 2>&1 & PF=\$!; sleep 2; curl -s http://127.0.0.1:$LOCAL_PORT/healthz; RC=\$?; kill \$PF >/dev/null 2>&1 || true; exit \$RC")"

printf 'deployment_image=%s\n' "$image_ref"
printf 'pod=%s\n' "$pod_name"
printf 'healthz=%s\n' "$(printf '%s' "$healthz_json" | tr -d '\n')"
