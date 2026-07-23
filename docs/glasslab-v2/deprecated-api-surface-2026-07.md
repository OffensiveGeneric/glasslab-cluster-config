# Deprecated API Surface 2026-07

Status: current compatibility policy

Date: 2026-07-23

The primary Glasslab operator surface is now:

```text
OpenCode -> repo-owned scripts -> workflow-api run/control endpoints
```

The API paths that existed for OpenClaw/WhatsApp-era session bootstrapping,
literature harvest, paper queues, and paper-derived one-shot pipelines are now
compatibility-only. They remain callable for old tests and old scripts, but new
operator flows should not build on them.

## Current Paths

Use these for new learning-task operation:

- `GET /healthz`
- `GET /workflow-families`
- `GET /workflow-families/{workflow_id}/execution-preflight`
- `POST /experiments/runs`
- `POST /experiments/runs/{run_id}/results`
- `POST /experiments/compare`
- autoresearch campaign endpoints when the run has an explicit evaluator
  contract

For local operation, prefer scripts:

- `scripts/glasslab-opencode.sh`
- `scripts/submit-learning-task.sh`
- `scripts/smoke-test-v2.sh`
- `scripts/check-workflow-api-provenance.sh`

## Deprecated Compatibility Paths

These are marked deprecated in the OpenAPI schema:

- `POST /research-sessions/start-literature-search`
- `POST /research-sessions/bootstrap`
- `GET /research-sessions/bootstrap-status`
- `POST /paper-pipelines/fresh-paper`
- `POST /paper-pipelines/from-research-problem`
- `POST /paper-pipelines/from-latest-research-problem`
- `POST /research-problems`
- `GET /research-problems/latest`
- `POST /paper-intake-queues/from-research-problem`
- `GET /paper-intake-queues`
- `GET /paper-intake-queues/latest`
- `GET /paper-intake-queues/{queue_id}`
- `POST /paper-intake-queues/{queue_id}/stage-next-intake`
- session-scoped `research-problem`, `literature-digest`,
  `paper-intake-queue`, `literature-harvest`, `external-literature-search`,
  and `paper-intake` skill routes

## Replacement Rule

If the operator wants to run a learning task, do not start a literature search
or paper pipeline. Submit a bounded workload:

```bash
./scripts/submit-learning-task.sh "Run a bounded metric-search baseline"
```

If a model needs context, let OpenCode read local docs, inspect repo files, and
call the run/control scripts. Do not make the chat layer stage literature
queues before a job can launch.

## Removal Criteria

Do not delete these routes until:

- current tests no longer depend on the literature/session pipeline as a live
  product path
- old OpenClaw/WhatsApp tool callers are either removed or explicitly pinned to
  a compatibility profile
- docs no longer teach literature-first session initiation as the default path
- any useful source-document ingestion behavior has a smaller replacement that
  is not coupled to paper queues
