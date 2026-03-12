#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_FILE="$ROOT/kubeadm/agent-stack/12-agent-secrets.yaml"
if [[ ! -f "$SECRETS_FILE" ]]; then
  SECRETS_FILE="$ROOT/kubeadm/agent-stack/12-agent-secrets.example.yaml"
  echo "using example secret manifest: $SECRETS_FILE"
fi
kubectl apply -f "$ROOT/kubeadm/agent-stack/00-namespace.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/02-persistent-volume-claims.yaml"
kubectl apply -f "$SECRETS_FILE"
kubectl apply -f "$ROOT/kubeadm/agent-stack/10-vllm-config.yaml"
kubectl apply -f "$ROOT/kubeadm/agent-stack/11-vllm-deployment.yaml"
