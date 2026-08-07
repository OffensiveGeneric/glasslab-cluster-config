#!/bin/bash
set -euo pipefail

API_BASE="${GLASSLAB_EXO_API_BASE:-http://127.0.0.1:52415}"
MODEL="${GLASSLAB_EXO_MODEL:-mlx-community/Qwen3-Coder-Next-4bit}"
RDMA_IFACE="${GLASSLAB_EXO_RDMA_IFACE:-rdma_en5}"
INTERVAL="${GLASSLAB_EXO_RECONCILE_INTERVAL:-30}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

needs_probe=1
placement_grace_until=0

while true; do
  state=$(/usr/bin/curl -fsS --max-time 5 "${API_BASE}/state" 2>/dev/null || true)
  if [[ -z "$state" ]]; then
    log "master API unavailable"
    sleep "$INTERVAL"
    continue
  fi

  if ! printf '%s' "$state" | /usr/bin/jq -e --arg iface "$RDMA_IFACE" '
    (.topology.nodes | length) == 2 and
    ([
      .topology.connections
      | to_entries[]?.value
      | to_entries[]?.value[]?
      | select(.sourceRdmaIface? == $iface and .sinkRdmaIface? == $iface)
    ] | length) >= 2
  ' >/dev/null; then
    needs_probe=1
    log "waiting for the two-node ${RDMA_IFACE} topology"
    sleep "$INTERVAL"
    continue
  fi

  instance_ids=$(printf '%s' "$state" | /usr/bin/jq -r --arg model "$MODEL" '
    .instances
    | to_entries[]?
    | select([.value | .. | strings | select(. == $model)] | length > 0)
    | .key
  ')

  if [[ -n "$instance_ids" ]]; then
    if (( needs_probe == 0 )); then
      sleep "$INTERVAL"
      continue
    fi

    probe_payload=$(/usr/bin/jq -nc --arg model "$MODEL" '{
      model: $model,
      messages: [{role: "user", content: "ping"}],
      max_tokens: 1,
      temperature: 0
    }')
    probe_code=$(/usr/bin/curl -sS --max-time 120 -o /dev/null -w '%{http_code}' \
      -H 'Content-Type: application/json' \
      --data-binary "$probe_payload" \
      "${API_BASE}/v1/chat/completions" || true)

    if [[ "$probe_code" == "200" ]]; then
      needs_probe=0
      placement_grace_until=0
      log "verified inference for ${MODEL}"
      sleep "$INTERVAL"
      continue
    fi

    now=$(date +%s)
    if (( now < placement_grace_until )); then
      log "placement is still starting; inference returned HTTP ${probe_code}"
      sleep "$INTERVAL"
      continue
    fi

    log "removing stale instance after inference returned HTTP ${probe_code}"
    while IFS= read -r instance_id; do
      [[ -n "$instance_id" ]] || continue
      /usr/bin/curl -fsS --max-time 30 -X DELETE \
        "${API_BASE}/instance/${instance_id}" >/dev/null || true
    done <<< "$instance_ids"
    sleep "$INTERVAL"
    continue
  fi

  previews=$(/usr/bin/curl -fsS --max-time 15 --get \
    --data-urlencode "model_id=${MODEL}" \
    "${API_BASE}/instance/previews" 2>/dev/null || true)
  instance=$(printf '%s' "$previews" | /usr/bin/jq -c '
    first(
      .previews[]?
      | select(
          .error == null and
          .sharding == "Pipeline" and
          .instance_meta == "MlxJaccl" and
          (.memory_delta_by_node | length) == 2
        )
      | .instance
    )
  ' 2>/dev/null || true)

  if [[ -z "$instance" || "$instance" == "null" ]]; then
    log "no approved two-node Pipeline + MlxJaccl placement is available"
    sleep "$INTERVAL"
    continue
  fi

  payload=$(/usr/bin/jq -nc --argjson instance "$instance" '{instance: $instance}')
  if /usr/bin/curl -fsS --max-time 30 -X POST \
    -H 'Content-Type: application/json' \
    --data-binary "$payload" \
    "${API_BASE}/instance" >/dev/null; then
    needs_probe=1
    placement_grace_until=$(($(date +%s) + 180))
    log "submitted two-node placement for ${MODEL}"
  else
    log "failed to submit placement for ${MODEL}"
  fi

  sleep "$INTERVAL"
done
