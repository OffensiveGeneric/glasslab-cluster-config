# OpenClaw Gateway

OpenClaw is the operator shell for Glasslab v2, not the experiment brain.

## Why it sits in front

- It keeps human-facing sessions and routing separate from backend execution.
- It can route literature work, workflow submission, and reporting without embedding infrastructure logic in prompts.
- It allows policy and tool restrictions to live in tracked config instead of hidden runtime state.

## Runtime contract

- source repo config lives under `services/openclaw-config`
- `scripts/export-openclaw-config.sh` renders the native OpenClaw runtime bundle
- the deployment mounts the exported bundle at `/var/lib/openclaw/runtime`
- the native config file lives at `/var/lib/openclaw/runtime/openclaw.json`
- generated workspaces live at `/var/lib/openclaw/runtime/workspaces/<agent>/`
- the raw repo-managed source tree is mirrored at `/var/lib/openclaw/runtime/glasslab-config/`

## Agent separation

- `operator`: receives user goals and routes them to approved backend paths
- `literature`: extracts structured method details from papers and notes
- `designer`: maps structured requests to approved workflow families
- `reporter`: summarizes artifacts and evaluator output for humans

## Default disabled tools

The default policy should deny:

- arbitrary shell execution
- mutating `kubectl` commands
- filesystem mutation tools such as `write`, `edit`, and `apply_patch`
- filesystem writes outside the approved workspace/config path
- arbitrary outbound HTTP requests
- Git push or repo mutation outside reviewed workflow paths

OpenClaw should only submit approved internal API calls and only after the request has been mapped to a declared workflow family or reporting path.

## Internal service references

- `workflow-api`: `http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080`
- `vLLM`: `http://vllm.glasslab-agents.svc.cluster.local:8000/v1`

These URLs are generated into the native runtime config by `scripts/export-openclaw-config.sh` and should never be replaced with localhost or port-forward addresses in the committed manifests.
