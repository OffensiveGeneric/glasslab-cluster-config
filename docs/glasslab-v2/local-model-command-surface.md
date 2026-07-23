# Local Model Command Surface

Status: current target surface

Date: 2026-07-23

Glasslab should not require WhatsApp as the primary way to operate learning
tasks.

The cleaner target is:

```text
human operator
      |
      v
OpenCode using the lab exo/OpenAI-compatible model endpoint
      |
      | shell/tools call repo-owned scripts
      v
workflow-api
      |
      v
Kubernetes Jobs + artifacts + evaluator records
```

In this shape, WhatsApp is only an optional adapter. It is not the core product
interface and it is not required for job control.

## Why This Is Simpler

WhatsApp added several layers before the operator reached the actual run
control plane:

```text
WhatsApp -> gateway -> ingress -> router -> workflow-api
```

That path is useful for remote phone access, but it is not the right default
for development and lab operation.

For local work, the operator already wants a model that can read the repo, run
commands, inspect logs, and call the same scripts a human would call. OpenCode
is a better primary surface for that.

## Current Primary Surface

Use:

```bash
./scripts/glasslab-opencode.sh
```

or a one-shot prompt:

```bash
./scripts/glasslab-opencode.sh "Check v2 health, then explain the latest run state."
```

The launcher uses:

- exo/OpenAI-compatible API: `GLASSLAB_EXO_API_BASE`
- model id: `GLASSLAB_OPENCODE_MODEL`
- default model: `mlx-community/Qwen3-Coder-Next-4bit`
- fallback OpenCode binary: `/home/gr66ss/.npm-global/bin/opencode`

If the 70B/Qwen-coder model is registered under a different exo model id, set
it explicitly:

```bash
GLASSLAB_OPENCODE_MODEL="<exo model id>" ./scripts/glasslab-opencode.sh
```

## What The Model Should Use

The model should operate Glasslab through repo-owned scripts and stable backend
endpoints, not through chat-gateway internals.

Preferred scripts:

- `scripts/research-session-cli.sh`
- `scripts/submit-learning-task.sh`
- `scripts/smoke-test-v2.sh`
- `scripts/check-workflow-api-provenance.sh`
- `scripts/rollout-workflow-api-live.sh`

Preferred backend:

- `workflow-api`

Preferred run endpoint:

- `POST /experiments/runs`

Preferred learning workload:

- `workload_id=metric-search-v0`

## Relationship To WhatsApp

WhatsApp remains useful as:

- a remote notification surface
- a narrow command adapter
- a future convenience layer for simple status and approval actions

WhatsApp should not be required for:

- submitting learning tasks
- comparing runs
- debugging cluster state
- operating the repo
- talking to the lab model

## Relationship To Exo

Exo is the local model-serving lane.

It provides an OpenAI-compatible API that OpenCode can use as a provider. Exo
does not own workflow state or Kubernetes execution. It only supplies model
inference for the operator shell.

## Boundary

OpenCode can use shell tools to operate Glasslab, but `workflow-api` remains the
control plane.

That means durable truth still lives in:

- Postgres / workflow-api records
- artifact bundles under the artifacts plane
- committed repo state
- `.44` for actual live cluster state

The model is an operator interface, not a second scheduler.
