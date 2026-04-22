# Product Cleanup 2026-04

This note is the explicit cleanup spec for Glasslab v2.

The repo no longer has one architecture problem. It has a path-overlap problem.

The cleanup goal is:

- keep one primary path per concern
- demote everything else
- stop presenting historical experiments as live product commitments

This document is intentionally opinionated. It is not a diary.

## Primary Product

Glasslab's primary product is:

- a runner-first research system
- deterministic operator control
- backend-owned session and run state
- bounded experiment execution
- explicit comparison and follow-on mutation

The primary control surface is:

- `whatsapp-gateway -> research-ingress -> research-command-router -> workflow-api`

The primary commands are:

- `!start`
- `!status`
- `!run`
- `!next`
- `!compare`

The primary control plane is:

- `workflow-api`

The primary metadata/system-of-record target is:

- `Postgres`

The primary artifact/file plane is:

- shared filesystem and/or MinIO for documents, artifacts, logs, and reports

The primary bounded inference lane is:

- exo OpenAI-compatible serving

## Secondary

These are still allowed, but they are not the product center.

### OpenClaw

OpenClaw is secondary.

It may remain useful for:

- optional chat
- bounded summaries
- read-only conversational help

It is not the command router.
It is not the workflow brain.
It is not required for the five primary command turns.

### Granular debug commands

The wider command/debug surface remains acceptable for operators, but it is not
the main UX.

Examples:

- `!research`
- `!more-papers`
- `!next-paper`
- `!interpret`
- `!design`
- `!preflight`
- `!start-autoresearch`
- `!launch-batch`
- `!decide-batch`

These should be treated as operator/debug tools, not product headline behavior.

## Deprecated

These are the first things to demote in docs, config, and operator expectations.

### 1. OpenClaw as a critical-path operator shell

Deprecate the story that OpenClaw is the primary operator surface.

Why:

- the repo-owned deterministic command path now exists
- OpenClaw command mediation was the main reliability failure
- live validation already proved the primary command loop can work with
  `glasslab-openclaw` scaled to `0`

High-signal conflicting files:

- `docs/glasslab-v2/operator-access-recommendation.md`
- `docs/glasslab-v2/research-pipeline-target.md`
- `docs/glasslab-v2/bounded-agent-architecture.md`
- `docs/glasslab-v2/openclaw-gateway.md`
- `docs/glasslab-v2/overview.md`

Required cleanup:

- stop describing OpenClaw as the front door or operator shell in current-state docs
- keep it explicitly optional
- keep command routing impossible to confuse with chat fallback

### 2. Old Ollama-backed operator / stage-agent assumptions

Deprecate the old Mac-Ollama story as current product truth.

That includes:

- `.23` `qwen3:30b`
- `.12` `qwen3:14b`
- native Ollama OpenClaw as the normal control/inference story

Why:

- the bounded-agent lane has already been moved in repo state toward the exo endpoint
- the deterministic command path no longer depends on those models
- keeping these paths as "current" makes the product look like it has multiple
  equally valid backend stories when it does not

High-signal files:

- `docs/glasslab-v2/README.md`
- `docs/glasslab-v2/ollama-native-openclaw.md`
- `docs/glasslab-v2/mac-studio-inference.md`
- `docs/glasslab-v2/resume-next-session-2026-03-24.md`
- `docs/glasslab-v2/live-state-2026-03-28.md`
- `docs/glasslab-v2/live-state-2026-03-30.md`
- `docs/glasslab-v2/implemented-vs-discussed-2026-03-30.md`

Required cleanup:

- mark these paths historical or legacy
- stop listing them in current summaries as if they are still the default
- keep only the exo-backed bounded-agent lane as the current backend story

### 3. JSON-on-artifacts-share as the long-term metadata store

Deprecate the idea that the JSON store is acceptable as the real metadata brain.

Current reality:

- `workflow-api` still supports only `memory` and `json`
- current durable path is:
  - `GLASSLAB_WORKFLOW_API_STORE_BACKEND=json`
  - `/mnt/artifacts/workflow-api/state/run-store.json`

Why this should be deprecated:

- records and files are mixed together on the same share
- session/stage state is being treated like a blob artifact
- the canonical stack already says Postgres should own records

High-signal files:

- `services/workflow-api/app/config.py`
- `services/workflow-api/README.md`
- `docs/glasslab-v2/state-and-storage-map-2026-03-27.md`

Required cleanup:

- implement Postgres-backed workflow/session store
- import JSON state once
- leave artifacts and documents on filesystem/MinIO
- stop calling JSON-backed state a steady-state design

### 4. Broad external literature search as a primary product promise

Deprecate "literature search" as a headline product capability.

Keep:

- manual source ingestion
- controlled paper intake
- source document storage
- bounded interpretation from known sources

Deprecate as primary:

- broad automated literature search
- open-ended harvester claims
- "start a literature search" as the main product identity

Why:

- it has not met the quality bar
- it dilutes the runner-first product
- the repo already says the literature side is secondary

High-signal files:

- `docs/glasslab-v2/bounded-experiment-runner-priority.md`
- `docs/glasslab-v2/research-assistant-implementation-checklist.md`
- `docs/glasslab-v2/research-assistant-infra-proposal.md`
- `docs/glasslab-v2/research-assistant-ux-boundary.md`
- `docs/glasslab-v2/external-literature-path.md`
- `services/workflow-api/app/literature_routes.py`
- `services/workflow-api/app/config.py`

Required cleanup:

- rename the story from "literature pipeline" to "source intake and review"
- make external search feature-flagged and clearly secondary
- stop centering the operator UX on literature-first messaging

### 5. `latest` aliases as an operator-facing default

Deprecate the broad use of `research-sessions/latest/...` as the main surface.

Why:

- sender-pinned session behavior is the real UX boundary
- "latest" is ambiguous in a multi-session or multi-sender world
- the repo still exposes many `latest` aliases inherited from earlier CLI and
  debugging assumptions

High-signal files:

- `services/workflow-api/README.md`
- `services/workflow-api/app/literature_routes.py`
- `services/workflow-api/app/main.py`
- `services/workflow-api/app/autoresearch_routes.py`
- `docs/glasslab-v2/research-ingress.md`
- `docs/glasslab-v2/repo-review-2026-03-26.md`

Required cleanup:

- keep `latest` internally as a compatibility alias if necessary
- stop promoting it in current product docs
- make sender-pinned or explicit session-id semantics the main story

## Legacy / Reference Only

These should remain in the repo only as historical context, migration material,
or break-glass fallback.

### vLLM as a current product lane

The old in-cluster `vllm` story is legacy.

Representative files:

- `docs/model-serving.md`
- `docs/titanic-agent-stack.md`
- `docs/glasslab-v2/node02-role-decision.md`
- `docs/glasslab-v2/node02-interpretation-agent-experiment.md`
- older live-state notes under `docs/`

Keep only for:

- historical decisions
- old cluster bring-up context
- explicit fallback/reference material

### March live-state notebooks and resume notes as current architecture docs

Many `live-state-2026-03-*` and `resume-next-session-*` notes still contain
important history, but they should not be read as current architecture truth.

These should be clearly labeled historical snapshots, especially when they
contain:

- old model choices
- old control surfaces
- old staging assumptions
- old "latest" route expectations

### Manual local-image import as a normal deploy story

Manual import remains acceptable only as break-glass.

GHCR should be the only normal deployment path.

## Keep

These are coherent and should remain central.

### Deterministic command seam

- `whatsapp-gateway`
- `research-ingress`
- `research-command-router`
- `workflow-api`

### Backend-owned run lifecycle

- registry-backed workflow selection
- deterministic manifest creation
- explicit preflight
- explicit run creation
- deterministic comparison/reporting

### Private backend services

- `ClusterIP` by default
- no broad ingress
- one narrow human-facing surface only

### `.44` as admin/apply host for now

`.44` remains acceptable as:

- canonical apply host
- validation host
- local secret source of truth

This is an operational constraint, not a product identity.

## Stateful Object Decisions

These are the current decisions the cleanup spec should force.

### Sessions and stage metadata

Target:

- move to Postgres

Not acceptable as long-term primary store:

- JSON state on shared artifacts PVC

### Source documents

Keep as files/objects:

- filesystem-backed source documents on shared storage, or MinIO if/when chosen

### Run artifacts and logs

Keep as files/objects:

- artifacts share and/or MinIO

### Chat/session transcript state

Primary transcript ownership should live in the repo-owned gateway/control
surface, not in OpenClaw as a hidden dependency.

### OpenClaw state

Only keep if OpenClaw is explicitly retained as a secondary conversational
surface.

If so:

- credentials and auth state remain operational concerns
- they are not product-critical state anymore

## Concrete Removal / Rewrite Candidates

First-pass cleanup targets:

1. Rewrite or mark historical:
   - `docs/glasslab-v2/operator-access-recommendation.md`
   - `docs/glasslab-v2/research-pipeline-target.md`
   - `docs/glasslab-v2/ollama-native-openclaw.md`
   - `docs/glasslab-v2/resume-next-session-2026-03-24.md`
   - `docs/glasslab-v2/live-state-2026-03-28.md`
   - `docs/glasslab-v2/live-state-2026-03-30.md`

2. Update current summary docs to remove stale current-state claims:
   - `docs/glasslab-v2/README.md`
   - `docs/glasslab-v2/overview.md`
   - `README.md`

3. Demote literature-first UX wording in:
   - `docs/glasslab-v2/research-assistant-implementation-checklist.md`
   - `docs/glasslab-v2/research-assistant-infra-proposal.md`
   - `docs/glasslab-v2/research-assistant-ux-boundary.md`
   - `docs/glasslab-v2/external-literature-path.md`

4. Replace JSON-store assumptions in code and docs:
   - `services/workflow-api/app/config.py`
   - `services/workflow-api/README.md`
   - `docs/glasslab-v2/state-and-storage-map-2026-03-27.md`

5. Stop promoting `latest` in external-facing docs:
   - `services/workflow-api/README.md`
   - `docs/glasslab-v2/research-ingress.md`

## Near-Term Execution Order

1. Rewrite current summary docs so they stop contradicting the canonical stack.
2. Mark OpenClaw-first and old Ollama docs as deprecated/historical.
3. Narrow the product story from "literature pipeline" to "source intake and bounded experiments."
4. Implement Postgres store support and cut `workflow-api` over from JSON.
5. Reduce public/current references to `latest` aliases in docs and operator flows.
6. Sweep remaining vLLM and old Ollama references into legacy/reference sections.

## Bottom Line

The main cleanup principle is:

- one canonical control surface
- one canonical backend store for records
- one canonical bounded inference story
- one honest statement about literature quality

Glasslab does not need more options.
It needs fewer implied promises.
