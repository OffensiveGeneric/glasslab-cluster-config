#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY_DIR="$ROOT_DIR/services/workflow-registry/definitions"

python3 - "$REGISTRY_DIR" <<'PY'
import json
import sys
from pathlib import Path

registry_dir = Path(sys.argv[1])
required_keys = {
    'workflow_id',
    'display_name',
    'workflow_family',
    'description',
    'required_inputs',
    'allowed_models',
    'runner_image',
    'evaluator_type',
    'expected_artifacts',
    'resource_profile',
    'approval_tier',
}

workflow_ids = set()
for path in sorted(registry_dir.glob('*.json')):
    payload = json.loads(path.read_text())
    missing = sorted(required_keys - payload.keys())
    if missing:
        raise SystemExit(f'{path}: missing required keys: {", ".join(missing)}')
    workflow_id = payload['workflow_id']
    if workflow_id in workflow_ids:
        raise SystemExit(f'duplicate workflow_id detected: {workflow_id}')
    workflow_ids.add(workflow_id)
    print(f'validated {workflow_id} from {path.name}')

print(f'validated {len(workflow_ids)} workflow definitions')
PY
