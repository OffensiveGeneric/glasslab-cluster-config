# Repo Review 2026-03-26

This note captures the current architecture concerns after the March 25-26 push to make Glasslab feel more like a stateful research assistant than a narrow run launcher.

The goal here is not to propose a rewrite. It is to make the current risk shape explicit and to identify the next bounded refactors that buy durability and clarity quickly.

## Current strengths

- `workflow-registry` is still the strongest contract boundary in the repo.
- OpenClaw remains intentionally narrow, which is the right operating model.
- research sessions are a better top-level product object than workflow families for conversational work.
- the bounded stage-agent split is still directionally correct:
  - intake
  - interpretation
  - assessment
  - design

## Current concerns

### 1. `workflow-api` is now a god service

`workflow-api` currently owns too many independent concerns inside one deployment and, in practice, one large module:

- intake normalization
- source-document ingestion
- paper-intake queue orchestration
- interpretation fallback
- assessment fallback
- design fallback
- schedule handling
- approved reruns
- execution preflight
- Kubernetes Job submission

Relevant paths:

- `/home/gr66ss/cluster-config/services/workflow-api/app/main.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/persistence.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/job_submission.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/execution_preflight.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/config.py`

This was the right iteration move. It is now the main maintainability risk.

### 2. The product model has shifted toward sessions

The system increasingly behaves as if the primary object is a research session, not a workflow family.

Session state now naturally groups:

- problem
- queue
- document
- intake
- interpretation
- assessment
- design
- run

Workflow families are increasingly execution templates:

- `generic-tabular-benchmark`
- `literature-to-experiment`
- `replication-lite`

The API and operator surface should keep moving toward:

- sessions as primary objects
- skills/stages as bounded backend capabilities
- execution templates as a later-stage concern

### 3. Global `latest` routes are still too important

The repo still leans heavily on mutating convenience aliases like:

- `POST /design-drafts/from-latest-intake`
- `POST /runs/from-latest-design-draft`
- `GET /research-sessions/latest/context`
- `POST /research-sessions/latest/paper-intake-queues/stage-next-intake`

These are useful for operator ergonomics and no-arg tools, but they are risky for:

- retries
- concurrency
- background automation
- multi-user operation

The right shape is:

- keep `latest` for convenience reads
- prefer session-scoped and ID-scoped mutating routes
- keep `latest` mutators only as compatibility aliases

### 4. Durability still does not match the docs

The docs increasingly describe durable state, but `workflow-api` still boots around in-memory persistence by default.

The main risk is not just run history. It is loss of the new session-centric research state:

- sessions
- queues
- source-document metadata
- interpretations
- assessments
- designs
- schedules
- schedule executions

Recommended boundary:

- Postgres first for structured metadata and current state
- object storage / filesystem for large artifacts and fetched source material
- append-only execution records for schedule runs and stage transitions

### 5. Registry truth and execution truth must stay aligned

This improved on 2026-03-26:

- registry definitions now expose machine-readable execution readiness
- execution preflight now checks submission support, not only cluster fit

But the repo should keep treating this as an active concern. If a workflow is declared but not runnable, the machine-readable status needs to say so clearly.

### 6. Too much slow work still sits inside request paths

The current API still performs failure-prone synchronous work directly in request handlers:

- source fetching
- PDF and HTML extraction
- ranker and harvester calls
- stage-agent calls
- end-to-end orchestration pipelines

That hurts:

- durability
- retry behavior
- observability
- operator trust

The next bounded fix is not a new service mesh. It is explicit operation records for slow work.

### 7. Scheduling is real but not durable enough yet

The repo now has:

- digest schedules
- approved rerun schedules
- `run-due` execution paths

That is enough to justify keeping scheduling inside `workflow-api` for now. It is not enough to call it durable.

The next requirements are:

- durable schedule state
- idempotent execution records
- explicit audit of why a schedule fired

### 8. Repo inheritability still needs work

A future maintainer still has to reconstruct too much from memory, issue comments, and `.44` context.

The repo needs clearer boundaries for:

- what is live
- what is committed
- what is still design-only
- what still depends on `.44`
- which storage and secret paths are authoritative

Follow-through note:

- `state-and-storage-map-2026-03-27.md` is now the canonical inventory for where session metadata, source documents, run artifacts, OpenClaw state, secrets, and images currently live.

## Immediate implementation candidates

### 1. Durable store backend for `workflow-api`

Target:

- replace default in-memory state with an explicit env-selected backend

First paths:

- `/home/gr66ss/cluster-config/services/workflow-api/app/persistence.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/main.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/config.py`

### 2. Promote session-scoped and ID-scoped routes over mutating `latest`

Target:

- make session and object IDs the primary contract
- keep `latest` as compatibility aliases

First paths:

- `/home/gr66ss/cluster-config/services/workflow-api/app/main.py`
- `/home/gr66ss/cluster-config/services/openclaw-config/plugins/workflow-api-tool/index.ts`
- `/home/gr66ss/cluster-config/services/openclaw-config/agents/operator/prompt.md`

### 3. Split `workflow-api/app/main.py` by concern

Target:

- reduce one-file risk without changing deployment boundaries

First candidate modules:

- `literature_sessions.py`
- `source_documents.py`
- `scheduler.py`
- `stages.py`

### 4. Add operation records for slow orchestration work

Target:

- make fetch, harvest, and stage-agent work inspectable and retryable

First paths:

- `/home/gr66ss/cluster-config/services/workflow-api/app/main.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/persistence.py`

### 5. Make scheduling durable and auditable before extracting it

Target:

- keep scheduling in `workflow-api` for now
- make schedule execution durable and idempotent first

First paths:

- `/home/gr66ss/cluster-config/services/workflow-api/app/main.py`
- `/home/gr66ss/cluster-config/services/workflow-api/app/persistence.py`

## Issue and label follow-through

The corresponding tracker work should be organized around:

- durable state
- session-first contracts
- operation records
- scheduling durability
- execution-template clarity
- repo inheritability

### Suggested labels

- `area:api`
- `area:docs`
- `area:execution`
- `area:inference`
- `area:infra`
- `area:openclaw`
- `area:scheduling`
- `area:storage`
- `area:workflow-api`
- `area:workflow-registry`
- `kind:design`
- `kind:docs`
- `kind:infra`
- `kind:refactor`
- `risk:high`
- `risk:medium`
- `risk:low`
- `state:design-gap`
- `state:live-gap`
- `state:repo-cleanup`

### Suggested milestones

- `M1 Durable State`
- `M2 Session-First API`
- `M3 Execution Truth Alignment`
- `M4 Durable Scheduling`
- `M5 GPU Workflow Families`
- `M6 Operator UX Cleanup`

See the issue tracker updates created alongside this note.
