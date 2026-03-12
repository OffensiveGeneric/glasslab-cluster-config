#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_MLFLOW=false
if [[ "${1:-}" == "--with-mlflow" ]]; then
  WITH_MLFLOW=true
fi
SECRETS_FILE="$ROOT/kubeadm/agent-stack/12-agent-secrets.yaml"
if [[ ! -f "$SECRETS_FILE" ]]; then
  SECRETS_FILE="$ROOT/kubeadm/agent-stack/12-agent-secrets.example.yaml"
  echo "using example secret manifest: $SECRETS_FILE"
fi
kubectl apply -f "$ROOT/kubeadm/agent-stack/00-namespace.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/01-rbac.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/02-persistent-volume-claims.yaml"
kubectl apply -f "$SECRETS_FILE"
kubectl apply -f "$ROOT/kubeadm/agent-stack/10-vllm-config.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/11-vllm-deployment.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/20-agent-api-config.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/21-agent-api-deployment.yaml"
if [[ "$WITH_MLFLOW" == true ]]; then
  kubectl apply -f "$ROOT/kubeadm/agent-stack/30-mlflow-optional.yaml"
fi
