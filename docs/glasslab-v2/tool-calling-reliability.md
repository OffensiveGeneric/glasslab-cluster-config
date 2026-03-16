# Tool-Calling Reliability

Last validated: 2026-03-16 on the live `.44` cluster path

## Current reliable pattern

The current reliable OpenClaw operator pattern for Glasslab v2 is:

- keep state-changing actions on repo-managed no-arg tools
- keep tool scope narrow and internal-only
- use repo-managed config to supply fixed backend payloads for the first validation lifecycle
- treat argumented tools as experimental until they succeed repeatedly under measurement

The known-good state-changing path remains:

- `workflow_api_create_validation_run`
- `workflow_api_get_last_validation_run`

These tools are backed by repo-managed config in `services/openclaw-config/bindings/workflow-api.yaml` and were revalidated during this audit.

## Live stack audited

The audited live path was:

- OpenClaw deployment in `glasslab-v2`
- operator agent runtime exported by `scripts/export-openclaw-config.sh`
- local provider `local-vllm-openai-compatible`
- vLLM deployment in `glasslab-agents`
- model `Qwen/Qwen3-4B-Instruct-2507`
- vLLM flags:
  - `--enable-auto-tool-choice`
  - `--tool-call-parser hermes`

The deployed operator tool surface seen by the model is intentionally small:

- `workflow_api_get_families`
- `workflow_api_create_validation_run`
- `workflow_api_get_last_validation_run`
- `workflow_api_get_family_by_id` (experimental)

The operator does not expose shell, filesystem mutation, cron, browser, or cluster mutation tools.

## Audit findings

### What is likely helping

- The working path uses no-arg tools for state-changing actions.
- The operator tool surface is already restricted to a few repo-managed plugin tools.
- Tool descriptions are short and specific.
- The validation run payload is fixed in repo config instead of being synthesized by the model.

### What is likely hurting

- The current OpenClaw operator path still relies on model-driven auto tool selection and model-generated arguments.
- The deployed `openclaw agent` CLI does not expose a clean per-turn `tool_choice` flag even though OpenClaw's bundled code clearly contains internal `tool_choice` plumbing.
- The local Qwen/vLLM path previously failed on a larger argumented tool with a 7-field schema by emitting `{}`.
- Even after shrinking the experimental tool to one required enum field, the model still failed to populate that field reliably.
- Once the model starts failing an argumented tool, later turns may skip the tool entirely and answer with a narrative fallback instead of retrying with valid arguments.

### Concrete evidence from this audit

- `openclaw agent --help` on the deployed pod shows no user-facing flag for pinned or required tool choice.
- Grepping `/app/dist` inside the OpenClaw image shows internal support for `tool_choice`, including `required` and pinned function-name modes.
- The current operator path does not expose that control cleanly from the provisioner workflow used here.

## Experimental tiny argumented tool

This audit added exactly one narrow experimental argumented tool:

- `workflow_api_get_family_by_id`

Properties:

- read-only
- one required field only: `workflow_id`
- `workflow_id` is constrained to the known approved workflow IDs exported from the registry
- backend action remains `GET /workflow-families`, followed by plugin-side filtering

This was intentionally chosen instead of an argumented create path because:

- it is low risk
- it has the smallest practical schema
- it is sufficient to test whether the model can reliably populate a single required argument

## Reliability harness

The repeatable harness is:

```bash
./scripts/check-openclaw-tool-calling.sh --attempts 5
```

It measures:

- whether the known-good no-arg create path still succeeds
- whether the known-good no-arg get path still succeeds
- whether the experimental argumented tool is selected
- whether required args are non-empty
- whether the audit log shows a schema-valid call
- whether the backend request succeeds

Evidence sources used by the harness:

- operator JSON response from `openclaw agent --local --agent operator --json`
- backend logs from `workflow-api`
- plugin audit log:
  - `/var/lib/openclaw/state/workflow-api-tool/tool-call-audit.jsonl`

## Results from the 2026-03-16 comparison

### No-arg baseline

No-arg create path:

- result: pass
- tool: `workflow_api_create_validation_run`
- backend proof: `POST /runs HTTP/1.1" 201 Created`
- created run id: `b40d97a36c9a4410af7186396ffd1ea6`

No-arg get path:

- result: pass
- tool: `workflow_api_get_last_validation_run`
- backend proof: `GET /runs/b40d97a36c9a4410af7186396ffd1ea6 HTTP/1.1" 200 OK`

### Tiny argumented path

Experimental path:

- tool: `workflow_api_get_family_by_id`
- prompt family: `generic-tabular-benchmark`
- attempts: `5`
- successes: `0`
- failures: `5`

Observed failure pattern:

- early attempts selected the tool but passed an empty `workflow_id`
- plugin audit entries recorded:
  - `requested_workflow_id: ""`
  - `error: "workflow_id is required"`
- later attempts sometimes produced no new audit event at all, which indicates the model stopped making a fresh valid tool call on that turn
- no successful backend `GET /workflow-families` request was produced by the experimental path during the harness run

## Decision

Current decision for Glasslab v2:

- keep no-arg tools for state-changing actions
- keep the current no-arg create/retrieve lifecycle as the safe default
- do not promote argumented tools into the main operator flow yet
- treat tiny argumented tools as experimental only

Based on the measured result in this audit, tiny argumented tools are not reliable enough yet on the current local Qwen + vLLM + OpenClaw path.

## Recommendation

Recommended operating policy today:

- keep no-arg tools for state-changing actions
- allow tiny argumented tools only as explicitly experimental, low-risk reads
- do not rely on argumented tools for required operator workflows until the model/runtime path changes or pinned tool-choice control is exposed cleanly

## Worthwhile next experiments

The next useful experiments are incremental, not architectural:

1. Test whether the deployed operator path can reach a lower-level OpenClaw or gateway interface that exposes explicit `tool_choice` for a named function.
2. Test a different local model or parser combination before widening any argumented tool surface.
3. If a stronger model becomes available locally, rerun `scripts/check-openclaw-tool-calling.sh` unchanged so the comparison stays apples-to-apples.
4. If a dedicated experimental operator agent is added later, keep it read-only and separate from the safe default operator path.
