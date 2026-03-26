#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAIL_LINES="${TAIL_LINES:-160}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"

oc_pod="$("$SCRIPT_DIR/k44.sh" -n "$NAMESPACE" get pods -l app.kubernetes.io/name=glasslab-openclaw -o jsonpath='{.items[0].metadata.name}')"
wf_pod="$("$SCRIPT_DIR/k44.sh" -n "$NAMESPACE" get pods -l app.kubernetes.io/name=glasslab-workflow-api -o jsonpath='{.items[0].metadata.name}')"

printf 'OPENCLAW_POD=%s\n' "$oc_pod"
printf 'WORKFLOW_API_POD=%s\n' "$wf_pod"
printf -- '--- OPENCLAW LOGS ---\n'
"$SCRIPT_DIR/k44.sh" -n "$NAMESPACE" logs "$oc_pod" --tail="$TAIL_LINES"
printf -- '--- WORKFLOW-API LOGS ---\n'
"$SCRIPT_DIR/k44.sh" -n "$NAMESPACE" logs "$wf_pod" --tail="$TAIL_LINES"
