#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${GLASSLAB_V2_NAMESPACE:-glasslab-v2}"
OPENCLAW_DEPLOY="${GLASSLAB_OPENCLAW_DEPLOY:-glasslab-openclaw}"
WORKFLOW_API_DEPLOY="${GLASSLAB_WORKFLOW_API_DEPLOY:-glasslab-workflow-api}"
ATTEMPTS=5
SINCE_SECONDS=120
AUDIT_PATH="/var/lib/openclaw/state/workflow-api-tool/tool-call-audit.jsonl"
RUN_STATE_PATH="/var/lib/openclaw/state/workflow-api-tool/last-validation-run.json"
SUMMARY_PATH=""

usage() {
  cat <<'USAGE'
Usage: check-openclaw-tool-calling.sh [--attempts N] [--summary-path PATH]

Run a simple OpenClaw tool-calling reliability check against the live Glasslab v2 deployment.

The check includes:
- the known-good no-arg create-validation-run path
- the known-good no-arg get-last-validation-run path
- repeated attempts against the tiny experimental argumented workflow family lookup tool
USAGE
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[check-openclaw-tool-calling] missing command: %s\n' "$1" >&2
    exit 1
  }
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --attempts)
      ATTEMPTS="$2"
      shift 2
      ;;
    --summary-path)
      SUMMARY_PATH="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '[check-openclaw-tool-calling] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

need_cmd kubectl
need_cmd python3

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

run_agent() {
  local prompt="$1"
  local output_path="$2"
  kubectl -n "$NAMESPACE" exec "deploy/${OPENCLAW_DEPLOY}" -- \
    openclaw agent --local --agent operator --json --message "$prompt" >"$output_path"
}

pod_read() {
  local command="$1"
  kubectl -n "$NAMESPACE" exec "deploy/${OPENCLAW_DEPLOY}" -- sh -lc "$command"
}

audit_count() {
  pod_read "test -f '$AUDIT_PATH' && wc -l < '$AUDIT_PATH' || echo 0" | tr -d '[:space:]'
}

last_audit_json() {
  pod_read "tail -n 1 '$AUDIT_PATH'"
}

state_run_id() {
  local payload
  payload="$(pod_read "cat '$RUN_STATE_PATH'")"
  RUN_STATE_JSON="$payload" python3 - <<'PY'
import json
import os
payload = json.loads(os.environ["RUN_STATE_JSON"])
print(payload["run_id"])
PY
}

log_match() {
  local pattern="$1"
  kubectl -n "$NAMESPACE" logs "deploy/${WORKFLOW_API_DEPLOY}" --since="${SINCE_SECONDS}s" | grep -E "$pattern" | tail -n 1 || true
}

parse_audit_field() {
  local json_payload="$1"
  local field_path="$2"
  AUDIT_JSON="$json_payload" python3 - "$field_path" <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["AUDIT_JSON"])
value = payload
for segment in sys.argv[1].split("."):
    value = value[segment]
if isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(value)
PY
}

assert_audit() {
  local json_payload="$1"
  local expected_tool="$2"
  local expected_status="$3"
  local extra_check="${4:-}"
  AUDIT_JSON="$json_payload" python3 - "$expected_tool" "$expected_status" "$extra_check" <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["AUDIT_JSON"])
expected_tool = sys.argv[1]
expected_status = sys.argv[2]
extra_check = sys.argv[3]

if payload.get("tool") != expected_tool:
    raise SystemExit(f"expected tool {expected_tool!r}, got {payload.get('tool')!r}")
if payload.get("status") != expected_status:
    raise SystemExit(f"expected status {expected_status!r}, got {payload.get('status')!r}")
if extra_check:
    field, expected = extra_check.split("=", 1)
    actual = payload.get(field)
    if actual != expected:
        raise SystemExit(f"expected {field!r} to be {expected!r}, got {actual!r}")
print("ok")
PY
}

extract_payload_text() {
  local output_path="$1"
  python3 - "$output_path" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], "r", encoding="utf-8"))
print(payload["payloads"][0]["text"])
PY
}

RESULTS_JSON="$TMP_DIR/results.json"
cat >"$RESULTS_JSON" <<'JSON'
{
  "no_arg_create": null,
  "no_arg_get": null,
  "argumented_attempts": []
}
JSON

printf '[check-openclaw-tool-calling] verifying no-arg create path\n'
create_before="$(audit_count)"
CREATE_OUTPUT="$TMP_DIR/create.json"
run_agent \
  "Create the bounded Glasslab v2 validation run and report the run_id, acceptance status, and job submission receipt." \
  "$CREATE_OUTPUT"
create_after="$(audit_count)"
if (( create_after <= create_before )); then
  printf '[check-openclaw-tool-calling] expected a new audit event for create path\n' >&2
  exit 1
fi
create_audit="$(last_audit_json)"
assert_audit "$create_audit" "workflow_api_create_validation_run" "ok" >/dev/null
run_id="$(state_run_id)"
create_log="$(log_match 'POST /runs HTTP/1.1\" 201')"
create_text="$(extract_payload_text "$CREATE_OUTPUT")"
RESULTS_JSON="$RESULTS_JSON" CREATE_AUDIT="$create_audit" CREATE_TEXT="$create_text" CREATE_LOG="$create_log" RUN_ID="$run_id" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["RESULTS_JSON"])
payload = json.loads(path.read_text())
payload["no_arg_create"] = {
    "run_id": os.environ["RUN_ID"],
    "audit": json.loads(os.environ["CREATE_AUDIT"]),
    "response_text": os.environ["CREATE_TEXT"],
    "backend_log": os.environ["CREATE_LOG"],
}
path.write_text(json.dumps(payload, indent=2))
PY
printf '[check-openclaw-tool-calling] no-arg create ok run_id=%s\n' "$run_id"

printf '[check-openclaw-tool-calling] verifying no-arg get path\n'
get_before="$(audit_count)"
GET_OUTPUT="$TMP_DIR/get.json"
run_agent \
  "Fetch the last validation run and summarize its workflow, accepted status, and job submission receipt." \
  "$GET_OUTPUT"
get_after="$(audit_count)"
if (( get_after <= get_before )); then
  printf '[check-openclaw-tool-calling] expected a new audit event for get path\n' >&2
  exit 1
fi
get_audit="$(last_audit_json)"
assert_audit "$get_audit" "workflow_api_get_last_validation_run" "ok" "run_id=${run_id}" >/dev/null
get_log="$(log_match "GET /runs/${run_id} HTTP/1.1\\\" 200")"
get_text="$(extract_payload_text "$GET_OUTPUT")"
RESULTS_JSON="$RESULTS_JSON" GET_AUDIT="$get_audit" GET_TEXT="$get_text" GET_LOG="$get_log" RUN_ID="$run_id" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["RESULTS_JSON"])
payload = json.loads(path.read_text())
payload["no_arg_get"] = {
    "run_id": os.environ["RUN_ID"],
    "audit": json.loads(os.environ["GET_AUDIT"]),
    "response_text": os.environ["GET_TEXT"],
    "backend_log": os.environ["GET_LOG"],
}
path.write_text(json.dumps(payload, indent=2))
PY
printf '[check-openclaw-tool-calling] no-arg get ok run_id=%s\n' "$run_id"

successes=0
for attempt in $(seq 1 "$ATTEMPTS"); do
  printf '[check-openclaw-tool-calling] experimental attempt %s/%s\n' "$attempt" "$ATTEMPTS"
  attempt_before="$(audit_count)"
  attempt_output="$TMP_DIR/argumented-${attempt}.json"
  run_agent \
    "Use the workflow_api_get_family_by_id tool to fetch workflow_id generic-tabular-benchmark and report only its approval tier and resource profile." \
    "$attempt_output"
  attempt_after="$(audit_count)"
  audit_json=""
  backend_log=""
  status="fail"
  message=""
  if (( attempt_after > attempt_before )); then
    audit_json="$(last_audit_json)"
    backend_log="$(log_match 'GET /workflow-families HTTP/1.1\" 200')"
    if assert_audit "$audit_json" "workflow_api_get_family_by_id" "ok" "requested_workflow_id=generic-tabular-benchmark" >/dev/null 2>&1; then
      status="ok"
      message="tool selected with non-empty enum argument"
      successes=$((successes + 1))
    else
      message="tool or argument mismatch"
    fi
  else
    message="no new audit event"
  fi
  response_text="$(extract_payload_text "$attempt_output")"
  RESULTS_JSON="$RESULTS_JSON" ATTEMPT="$attempt" STATUS="$status" MESSAGE="$message" RESPONSE_TEXT="$response_text" BACKEND_LOG="$backend_log" AUDIT_JSON="$audit_json" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["RESULTS_JSON"])
payload = json.loads(path.read_text())
entry = {
    "attempt": int(os.environ["ATTEMPT"]),
    "status": os.environ["STATUS"],
    "message": os.environ["MESSAGE"],
    "response_text": os.environ["RESPONSE_TEXT"],
    "backend_log": os.environ["BACKEND_LOG"],
    "audit": json.loads(os.environ["AUDIT_JSON"]) if os.environ["AUDIT_JSON"] else None,
}
payload["argumented_attempts"].append(entry)
path.write_text(json.dumps(payload, indent=2))
PY
  printf '[check-openclaw-tool-calling] experimental attempt %s %s\n' "$attempt" "$status"
done

RESULTS_JSON="$RESULTS_JSON" ATTEMPTS="$ATTEMPTS" SUCCESSES="$successes" python3 - <<'PY'
import json
import os

payload = json.loads(open(os.environ["RESULTS_JSON"], "r", encoding="utf-8").read())
attempts = int(os.environ["ATTEMPTS"])
successes = int(os.environ["SUCCESSES"])
payload["argumented_summary"] = {
    "attempts": attempts,
    "successes": successes,
    "failures": attempts - successes,
}
open(os.environ["RESULTS_JSON"], "w", encoding="utf-8").write(json.dumps(payload, indent=2))
print(json.dumps(payload["argumented_summary"], indent=2))
PY

if [[ -n "$SUMMARY_PATH" ]]; then
  cp "$RESULTS_JSON" "$SUMMARY_PATH"
  printf '[check-openclaw-tool-calling] wrote summary to %s\n' "$SUMMARY_PATH"
else
  printf '[check-openclaw-tool-calling] summary file: %s\n' "$RESULTS_JSON"
fi
