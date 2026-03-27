#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
DEPLOYMENT="${GLASSLAB_OPENCLAW_DEPLOYMENT:-glasslab-openclaw}"

pod_name="$(ssh glasslab-44 "kubectl -n '$NAMESPACE' get pods -l app.kubernetes.io/name='$DEPLOYMENT' -o jsonpath='{.items[0].metadata.name}'")"
image_ref="$(ssh glasslab-44 "kubectl -n '$NAMESPACE' get deploy '$DEPLOYMENT' -o jsonpath='{.spec.template.spec.containers[0].image}'")"
provenance_json="$(ssh glasslab-44 "kubectl -n '$NAMESPACE' exec '$pod_name' -- sh -lc 'if [ -f /var/lib/openclaw/runtime/PROVENANCE.json ]; then cat /var/lib/openclaw/runtime/PROVENANCE.json; else printf \"{\\\"missing\\\":true,\\\"detail\\\":\\\"runtime provenance file not found\\\"}\\n\"; fi'")"

printf 'deployment_image=%s\n' "$image_ref"
printf 'pod=%s\n' "$pod_name"
printf 'provenance=%s\n' "$(printf '%s' "$provenance_json" | tr -d '\n')"
