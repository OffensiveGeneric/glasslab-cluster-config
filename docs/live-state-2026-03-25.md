# Live State Report: 2026-03-25

This note records what was validated from `.44` during the 2026-03-25 remote session.

It should be treated as a newer documented live-state checkpoint than `live-state-2026-03-24.md`.

## OpenClaw

Validated from `.44`:

- `glasslab-openclaw` remains live and healthy
- the active runtime is using native Ollama against `.23`
- `.23` `qwen3:30b` is now installed and serving as the main OpenClaw model
- native tool support is working again on this path

Validated operator-tool state:

- the safe no-arg workflow path is working again
- the generated no-arg exact-family lookup tools work live
- the tiny argumented `workflow_api_get_family_by_id` path is still not a trustworthy control surface

## Glasslab v2 Core

Validated from `.44`:

- `glasslab-workflow-api` is `Running`
- the live image is `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.13-local`
- `glasslab-interpretation-agent` is `Running`
- `glasslab-intake-agent` is now deployed and healthy
- the live image is `ghcr.io/offensivegeneric/glasslab-intake-agent:0.1.2-local`
- `glasslab-schedule-worker` is now deployed and healthy
- the live image is `ghcr.io/offensivegeneric/glasslab-schedule-worker:0.1.0-local`

Observed placement at validation time:

- `glasslab-workflow-api` on `node04`
- `glasslab-intake-agent` on `node05`
- `glasslab-schedule-worker` on `node05`

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

- ranker-assisted intake is deployed, but the first live prompt checked here did not yet produce an obviously reordered family list through `workflow-api`
- the old in-cluster `vllm` path on `node02` still exists and the GPU has not yet been reclaimed
