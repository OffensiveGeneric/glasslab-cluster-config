# Live State Report: 2026-03-25

This note records what was validated from `.44` during the 2026-03-25 remote session.

It should be treated as a newer documented live-state checkpoint than `live-state-2026-03-24.md`.

## OpenClaw

Validated from `.44`:

- `glasslab-openclaw` remains live and healthy
- the active runtime is now using native Ollama against `.12`
- the live agent model is `glasslab-ollama/qwen3:14b`
- WhatsApp is linked on the dedicated assistant number and the live pod is listening for inbound messages
- the new OpenClaw runtime includes the controlled-literature no-arg/latest-record operator tools
- the new OpenClaw runtime now points the literature path at the session-scoped skill/read surface in `workflow-api`
- native tool support is working on this path

Validated operator-tool state:

- the safe no-arg workflow path is working again
- the generated no-arg exact-family lookup tools work live
- the tiny argumented `workflow_api_get_family_by_id` path is still not a trustworthy control surface
- the brittle direct free-text research-problem tool was removed from the chat-facing surface in favor of staged/no-arg paths

## Glasslab v2 Core

Validated from `.44`:

- `glasslab-workflow-api` is `Running`
- the live image is `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.22-local`
- `glasslab-interpretation-agent` is `Running`
- `glasslab-intake-agent` is now deployed and healthy
- the live image is `ghcr.io/offensivegeneric/glasslab-intake-agent:0.1.2-local`
- `glasslab-schedule-worker` is now deployed and healthy
- the live image is `ghcr.io/offensivegeneric/glasslab-schedule-worker:0.1.0-local`

Additional live backend state:

- the controlled literature pipeline is now integrated in the live `workflow-api`
- paper-intake queues and source-document records are first-class backend objects
- research sessions now expose session-scoped skill routes for:
  - research problem
  - literature harvest
  - paper intake
  - interpretation
  - assessment
  - design
- research sessions now expose session-scoped read routes for:
  - research problem
  - queue
  - source document
  - intake
  - interpretation
  - assessment
  - design
- interpretation outputs now carry:
  - `literature_state_summary`
  - `research_gaps`
  - `bounded_experiment_ideas`
- those interpretation outputs now inform later assessment and design stages
- `workflow-api` now exposes execution preflight and applies registry-declared resource requests, limits, and node selectors at job-submission time

Observed placement at validation time:

- `glasslab-workflow-api` on `node04`
- `glasslab-intake-agent` on `node05`
- `glasslab-schedule-worker` on `node05`
- `glasslab-openclaw` on `node01`

## Intake And Ranker Lane

Validated from `.44`:

- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_ENABLED=true`
- `GLASSLAB_WORKFLOW_API_RANKER_ENABLED=true`
- direct `POST /intakes` works through the live `workflow-api`
- `intake-agent` health checks are green after copying the seed manifest into the image
- the bounded approved-source seed manifest is now part of the live intake-agent runtime

Additional live checks:

- the `.12` ranker health endpoint responds on `http://192.168.1.12:8181/healthz`
- direct ranker requests using the current `workflow-api` payload shape return ranked candidates

## Autonomous Schedule Lane

Validated from `.44`:

- `POST /digest-schedules` works live
- `POST /digest-schedules/run-due` works live
- `GET /scheduled-executions` returns the created execution record
- `glasslab-schedule-worker` is live as the bounded unattended worker service

Observed live result during validation:

- a due digest schedule executed successfully
- `result_status=ok`
- `operation_type=digest`

Current limitation:

- the approved-rerun lane is now fully revalidated live
- a naturally succeeded source run was used to create an approved rerun schedule
- `POST /approved-rerun-schedules/run-due` submitted an autonomous rerun successfully
- the produced rerun reached `status=succeeded`
- the produced rerun kept:
  - `run_purpose=approved-rerun`
  - `run_priority=autonomous`

## Remaining Live Gaps

- ranker-assisted intake is deployed, but still needs a tighter live proof that the reordered candidate set is materially different for a real literature prompt
- the current harness can validate declared execution shape before submission, but it does not yet introspect runner images for Python/package prerequisites
- the current workflow families are still CPU-oriented in practice; a dedicated coarse GPU experiment workflow family and runner image had not yet been added at that point

## Retired Today

Validated from `.44`:

- the old in-cluster `vllm` path on `node02` was retired
- `glasslab-openclaw` was fully cut over off `glasslab-vllm/Qwen/Qwen3-4B-Instruct-2507`
- `deploy/vllm` in `glasslab-agents` is now scaled to `0`
- the old `vllm` pod on `node02` terminated
- `kubectl describe node node02` now shows:
  - `nvidia.com/gpu     0         0`
  under allocated resources, so the GPU lane is reclaimed for future bounded backend work
