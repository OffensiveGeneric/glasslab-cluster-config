#!/usr/bin/env bash
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
CURL="${CURL:-curl}"
NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
HEALTH_PORT="${GLASSLAB_V2_HEALTH_PORT:-18081}"
EXPECTED_SERVICES=(glasslab-workflow-api glasslab-postgres glasslab-nats glasslab-minio)
PORT_FORWARD_PID=""
PORT_FORWARD_LOG=""

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[smoke-test-v2] missing command: %s\n' "$1" >&2
    exit 1
  }
}

cleanup() {
  if [[ -n "$PORT_FORWARD_PID" ]]; then
    kill "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
    wait "$PORT_FORWARD_PID" 2>/dev/null || true
  fi
  if [[ -n "$PORT_FORWARD_LOG" && -f "$PORT_FORWARD_LOG" ]]; then
    rm -f "$PORT_FORWARD_LOG"
  fi
}
trap cleanup EXIT

need_cmd "$KUBECTL"
need_cmd "$CURL"

printf '[smoke-test-v2] checking namespace %s\n' "$NAMESPACE"
"$KUBECTL" get namespace "$NAMESPACE" >/dev/null

printf '[smoke-test-v2] checking rollout status\n'
"$KUBECTL" -n "$NAMESPACE" rollout status deployment/glasslab-nats --timeout=120s
"$KUBECTL" -n "$NAMESPACE" rollout status deployment/glasslab-minio --timeout=120s
"$KUBECTL" -n "$NAMESPACE" rollout status deployment/glasslab-workflow-api --timeout=120s
"$KUBECTL" -n "$NAMESPACE" rollout status statefulset/glasslab-postgres --timeout=120s

printf '[smoke-test-v2] checking service inventory\n'
"$KUBECTL" -n "$NAMESPACE" get deploy,statefulset,svc

for service in "${EXPECTED_SERVICES[@]}"; do
  "$KUBECTL" -n "$NAMESPACE" get service "$service" >/dev/null
  printf '[smoke-test-v2] dns %s.%s.svc.cluster.local\n' "$service" "$NAMESPACE"
done

PORT_FORWARD_LOG="$(mktemp)"
"$KUBECTL" -n "$NAMESPACE" port-forward svc/glasslab-workflow-api "${HEALTH_PORT}:8080" >"$PORT_FORWARD_LOG" 2>&1 &
PORT_FORWARD_PID="$!"

for _ in $(seq 1 20); do
  if "$CURL" -fsS "http://127.0.0.1:${HEALTH_PORT}/healthz" >/dev/null; then
    break
  fi
  sleep 1
done

printf '[smoke-test-v2] workflow-api health response\n'
"$CURL" -fsS "http://127.0.0.1:${HEALTH_PORT}/healthz"
printf '\n'
