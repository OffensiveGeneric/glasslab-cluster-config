# OpenClaw Gateway

OpenClaw is the operator shell for Glasslab v2, not the experiment brain.

## Current live status

Validated from `.44` on 2026-03-24:

- the committed Deployment manifest still keeps `replicas: 0`
- the live Deployment has been deliberately scaled back up to `1`
- the live pod is running against the Mac-backed inference endpoint on `192.168.1.23`
- the first Mac cutover used Ollama's OpenAI-compatible `/v1` path
- that cutover is good enough for plain chat inference
- that cutover is not yet a valid replacement for the old tool-calling path
- the current live tool harness fails on the Mac-backed `deepseek-r1:32b` path with:
  - `400 registry.ollama.ai/library/deepseek-r1:32b does not support tools`

Reference:

- `../live-state-2026-03-24.md`
- `ollama-native-openclaw.md`

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
- the unpacked runtime directory is writable inside the running container so channel setup can persist one-time config normalization without mutating the repo-managed source tree
- the current WhatsApp-enabled runtime needs a larger memory envelope than the earlier tool-only path, so the Deployment reserves more memory than the first bare operator validation

## Agent separation

- `operator`: receives user goals and routes them to approved backend paths
- `literature`: extracts structured method details from papers and notes
- `designer`: maps structured requests to approved workflow families
- `reporter`: summarizes artifacts and evaluator output for humans

## First Operator Step

OpenClaw should treat the first meaningful operator turn as a session bootstrap step, not a workflow-family lookup.

Preferred flow:

- recover the latest research session if one already exists
- create a new session from the latest staged research problem when that is the approved entry point
- only fall back to intake, queue, design, or run actions after the required session state is present

Missing-state rule:

- if a required session, research problem, queue, or design record does not exist, say which prerequisite is missing
- give one concrete next step
- do not retry the same missing-state path with a different tool in the same turn
- if a backend route returns `404` for missing session state, stop there and surface the prerequisite gap plainly

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

If Glasslab moves primary inference to a separate host such as a Mac Studio, keep the committed provider YAML on the safe in-cluster default and export the runtime bundle with explicit overrides instead.

For plain OpenAI-compatible chat inference, an override like this still works:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="https://mac-studio.example.internal/v1" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="your-primary-model-id" \
./scripts/export-openclaw-config.sh
```

But for remote Ollama tool use, the current OpenClaw docs recommend native Ollama provider mode instead:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://mac-studio.example.internal:11434" \
GLASSLAB_OPENCLAW_PROVIDER_API="ollama" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="your-tool-capable-ollama-model" \
./scripts/export-openclaw-config.sh
```

That keeps the repo default conservative while letting the deployed OpenClaw runtime target the external inference tier in a way that is compatible with native Ollama tool behavior.

## First chat channel

WhatsApp is the first validation target.

Rationale:

- the bundled OpenClaw docs in the deployed image mark WhatsApp as production-ready
- the live image contains native WhatsApp Web channel support and routing guidance
- the current stack already supports a narrow direct-message allowlist and self-chat mode without expanding tool scope
- Signal remains a deferred option until there is a concrete operational reason to prefer it over the built-in WhatsApp path

Validation gate:

- the WhatsApp channel is exported into the live runtime only when `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml` defines `OPENCLAW_WHATSAPP_OWNER`
- the exported runtime should include `channels.whatsapp.defaultAccount=default` and `channels.whatsapp.accounts.default.authDir=/var/lib/openclaw/state/credentials/whatsapp/default`
- this keeps the default repo path safe and prevents accidental broad DM exposure when the owner number is not explicitly set

Current live nuance:

- the runtime still contains the WhatsApp channel block and the operator binding
- the owner number is still present in the live OpenClaw secret
- persisted WhatsApp credentials still exist on the OpenClaw state volume
- but the WhatsApp path has not yet been revalidated after the Mac cutover
- operationally, treat the channel path as configured but not freshly confirmed end-to-end on the current backend
