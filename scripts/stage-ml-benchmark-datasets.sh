#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
JOB=stage-ml-benchmark-datasets

kubectl -n "$NAMESPACE" delete job "$JOB" --ignore-not-found
kubectl apply -f \
  "$ROOT_DIR/kubeadm/glasslab-v2/jobs/50-stage-ml-benchmark-datasets.yaml"
kubectl -n "$NAMESPACE" wait \
  --for=condition=complete "job/$JOB" --timeout=600s
kubectl -n "$NAMESPACE" logs "job/$JOB"
