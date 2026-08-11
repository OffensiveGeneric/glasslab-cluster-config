# Glasslab System Audit — DeepSeek Read-Only Review

*Generated 2026-08-11 from repository state at main branch. Read-only audit; no live cluster data.*

## 1. Implemented vs. Documented / Planned

### Implemented and Deployed

| System | Evidence |
|--------|----------|
| **State machine** — 25 states covering full lifecycle from `CREATED` to `COMPLETE`, plus terminal states (`FAILED`, `CANCELLED`, `TIMED_OUT`) and pause/resume | `services/research-orchestrator/app/schemas.py:24-47`; `engine.py:62-4083` (all transitions) |
| **Dual-agent orchestration** — Honeydew (methodology/synthesis) and Beaker (implementation/analysis) with isolated OpenCode runtimes, per-agent workspaces, and structured turn-taking | `engine.py:119-276`; `AGENTS.md:65-79` |
| **Human-in-the-loop approval gates** — protocol approval, contract promotion, execution approval, final acceptance; all gated by Discord buttons | `engine.py:1508-1745`; `AGENTS.md:142-145` |
| **Bounded Kubernetes Job execution** — via `workflow-api`, with security context (non-root, no privileges, seccomp, no service-account token) | `services/workflow-api/app/job_submission.py:481-745` |
| **Immutable evaluation contracts** — signed with SHA-256 digests; evaluator inspects output deterministically; evaluator never runs inside the workload | `services/research-workspace-runner/runner.py:31`; `services/evaluator/app/main.py:22-30` |
| **Deterministic workspace runner** — verifies SHA-256 of input archives, enforces bidirectional dataset contracts, writes atomic terminal bundle via temp-then-rename | `services/research-workspace-runner/runner.py:131-299` |
| **Lexical knowledge retrieval (RAG)** — SQLite FTS5 with BM25 ranking, role-scoped per agent/turn, `knowledge://` citation URIs | `services/research-orchestrator/app/knowledge_manager.py:53-798`; merged via PR #124 |
| **Discord transport** — slash commands, threaded runs, button-based approvals, editable status messages | `services/research-orchestrator/app/discord_adapter.py`; `discord_controls.py` |
| **Recovery** — crash-recovery restores workspaces, backfills artifacts, re-enters correct workflow phase | `engine.py:3813-4083` |
| **Workflow API (3 storage backends)** — in-memory, JSON file, and live Postgres via psycopg with pgvector | `services/workflow-api/app/persistence.py:372-1345` |

### Implemented but Not Deployed / Partial

| System | Status |
|--------|--------|
| **Embedding-based semantic retrieval** | Not implemented — `docs/research-orchestrator.md` corrected to say "planned but not yet implemented" |
| **PostgreSQL migration (research-orchestrator)** | Not started — `TODO.md:36` (#97); orchestrator still uses SQLite at `main.py:81` |
| **Terminal checkpoint retry** | Not implemented — `HANDOFF.md:112-121` describes desired behavior; blocked on issue #92 |
| **Fashion-MNIST end-to-end run** | Not completed — `HANDOFF.md:108`; issue #101 |
| **Arbitrary-dataset generic run** | Not completed — `TODO.md:30` (#98); docs call it "outstanding" at `docs/research-orchestrator.md:11` |
| **Hermes runtime adapter** | Under evaluation — `HANDOFF.md:27-31`; issue #96 |

### Not Implemented (Planned / Aspirational Only)

| Item | Source |
|------|--------|
| Embedding cosine similarity for retrieval | `docs/research-orchestrator.md:245` (history: was documented, now corrected) |
| Ollama reranker integration | Same as above |
| `policy`, `methodology`, `verified_result` source types | `services/research-orchestrator/app/schemas.py:620-622` (comment only; not in enum) |
| Multi-replica orchestrator | `HANDOFF.md:163` (known risk) |

---

## 2. End-to-End Path: Research Request to Kubernetes Job

```
Human (Discord channel)
  | /research-start objective:"..."
  | /task-start archive:<zip> objective:"..."
  v
research-orchestrator (internal, single pod on node05)
  | POST /runs  ->  engine.create_run()
  |   +-- resolves evaluation contract
  |   +-- validates task preflight
  |   +-- creates Discord thread
  |   +-- prepares isolated workspaces (beaker-worktree, honeydew-worktree)
  |   +-- transitions CREATED -> PREPARING -> HONEYDEW_DRAFTING_PROTOCOL
  |
  | engine._draft_protocol()
  |   +-- Honeydew OpenCode process drafts program.md in isolated workspace
  |      -> AWAITING_PROTOCOL_APPROVAL  (human Discord approve/reject)
  |
  +-- [optional: contract drafting sub-flow if binding incompatible]
  |   +-- BEAKER_DRAFTING_CONTRACT -> HONEYDEW_REVIEWING_CONTRACT
  |   +-- -> AWAITING_CONTRACT_PROMOTION -> BEAKER_PLANNING
  |
  | engine._beaker_plan() / _beaker_implement()
  |   +-- Beaker OpenCode process plans workload, implements in worktree
  |      engine._honeydew_review()  -> AWAITING_EXECUTION_APPROVAL
  |
  | engine._submit_matrix()  -> JOB_QUEUED
  |   +-- HTTP POST to workflow-api /experiments/runs
  |
  v
workflow-api (internal, separate pod)
  | job_submission.py:submit_run()
  |   +-- renders V1Job spec: securityContext, resource limits, volumes
  |   +-- sets env vars: GLASSLAB_RUNNER_MANIFEST_JSON, GENERIC_CONFIG_JSON, etc.
  |   +-- kubectl apply -> Kubernetes Job
  |
  v
Kubernetes worker (node01-node05)
  | research-workspace-runner container
  |   +-- verifies SHA-256 digests of input archives
  |   +-- resolves dataset bindings (bidirectional contract check)
  |   +-- runs declared command under wall-clock timeout
  |   +-- writes terminal bundle: run_manifest.json, config.json,
  |       artifacts_index.json, status.json, logs/runner.log
  |
  v
orchestrator: engine.reconcile_run() (poll loop)
  |   +-- detects terminal job status
  |   +-- records durable artifacts
  |   +-- transitions JOB_RUNNING -> BEAKER_ANALYZING
  |
  | engine._analyze_results()  -> HONEYDEW_VERIFYING
  | engine._write_report()  -> AWAITING_FINAL_ACCEPTANCE  -> COMPLETE
  |
  v
Discord (status updates, artifact delivery, report visible in thread)
```

**Key files in this path:**
- Entry: `services/research-orchestrator/app/main.py:337` (POST /runs)
- State machine: `services/research-orchestrator/app/engine.py:62-4083`
- Job submission: `services/workflow-api/app/job_submission.py:481`
- Workload runtime: `services/research-workspace-runner/runner.py:302`
- Evaluation: `services/evaluator/app/main.py:22`
- Deployment: `kubeadm/glasslab-v2/research-orchestrator/20-deployment.yaml`

---

## 3. Three Highest-Risk Operational Gaps

### Risk 1: Single-replica orchestrator with SQLite is a single point of failure

- **What**: One pod on node05 with SQLite WAL on NFS-backed PVC. No failover, no read replicas, no connection pooling.
- **Impact**: If node05 goes down, all research runs freeze. NFS latency amplifies SQLite contention. Schema migrations require downtime.
- **Evidence**: `kubeadm/glasslab-v2/research-orchestrator/20-deployment.yaml:25` sets replicas=1; `main.py:81` uses `SqliteStore`. `HANDOFF.md:163` documents this as a known risk.
- **Planned**: PostgreSQL migration is issue #97.

### Risk 2: No terminal checkpoint retry — stalled runs are dead ends

- **What**: `TIMED_OUT`, `FAILED`, and `CANCELLED` states have no recovery path. The Wine clustering run (`39101d9c`) expired with a validated corrected proposal ready, but terminal runs cannot be resumed.
- **Impact**: Completed work (approved protocol, validated implementation, pending matrix) is trapped in dead runs. Every restart requires full re-protocol.
- **Evidence**: `engine.py:390-414` transitions to terminal states irreversibly; `HANDOFF.md:88-104` documents the Wine case. Issue #92 blocks P0 work (issue #100).
- **Fix**: Implement controlled retry/clone-from-terminal operation described in `HANDOFF.md:112-121`.

### Risk 3: Agent-turn latency against shared exo endpoint with no caching

- **What**: Both Honeydew and Beaker use the same Qwen model on a single two-node exo pair (`.17`/`.18`). Large evidence bundles compound the problem. No turn result caching, no evidence deduplication, no streaming response optimization.
- **Impact**: Runs take hours; turn timeouts are common. OpenCode runtime caches consume substantial shared storage.
- **Evidence**: `HANDOFF.md:48-50` (exo config), `HANDOFF.md:164-165` (known risk); `opencode_runtime.py:780-803` (watchdog enforces timeout, doesn't optimize); `TODO.md:25` (issue #93: compact evidence prompts).
- **Fix**: Issue #93 (compact prompts) is the immediate target. Longer term: Hermes evaluation (#96) and evidence deduplication.

---

## 4. Legacy / Titanic Paths (Reference-Only)

These services and paths are **not the current product surface** and should be treated as historical reference. Per `AGENTS.md:90-97`:

| Path / Service | Status | Why Reference-Only |
|----------------|--------|--------------------|
| `services/agent-api/` | Legacy Titanic v1 | Replaced by research-orchestrator; monolithic planner->submit pipeline with no human approval gates |
| `services/runner/` | Legacy Titanic v1 | 4 hardcoded ML pipelines (titanic, literature, GPU, contrastive); replaced by generic `research-workspace-runner` |
| `kubeadm/agent-stack/` | Legacy deployment | Titanic v1 deployment manifests; not the current research path |
| OpenClaw / WhatsApp adapters | Compatibility | `services/whatsapp-gateway/`, `whatsapp-web-bridge/`, `services/research-ingress/`, `services/research-command-router/` -- all are secondary compatibility adapters, not the Discord-based primary path |
| Stage-agent pipeline | Secondary | `services/intake-agent/`, `interpretation-agent/`, `design-agent/`, `assessment-agent/`, `ranker/` -- belong to the older stage-agent model; `docs/glasslab-v2/current/overview.md:142-151` says they "are not the primary product surface" |
| `!new` / `!plan` command vocabulary | Deprecated | Replaced by Discord slash commands (`/research-start`, `/task-start`, etc.) per `AGENTS.md:96-97` |

**What IS current:**
- `services/research-orchestrator/` -- primary orchestrator
- `services/research-workspace-runner/` -- bounded sandbox executor
- `services/workflow-api/` -- cluster execution control plane
- `services/evaluator/` -- deterministic post-run scoring
- `services/reporter/` -- deterministic post-run rendering
- `services/common/` -- shared schemas/contracts
- `services/schedule-worker/` -- cron trigger for digest cycles

---

## 5. Prioritized Five Concrete Next Tasks

### 1. Implement terminal checkpoint retry (P0)

- **Why**: Unblocks Wine clustering (#100) and all stalled runs. The only P0 task not yet started.
- **Files**: `services/research-orchestrator/app/engine.py` (new `clone_from_terminal` method, ~line 3754 after cancel_run), `services/research-orchestrator/app/state_machine.py` (new transition), `services/research-orchestrator/app/schemas.py` (new `parent_run_id` field on RunRecord)
- **Issue**: #92

### 2. Complete confirmed Wine clustering research run (P0)

- **Why**: Validates the full end-to-end loop with a known-good corrected proposal. Depends on #92.
- **Files**: `services/research-orchestrator/app/engine.py` (operates existing path), `docs/research-orchestrator-command-surface.md` (operator procedure)
- **Issue**: #100 (blocked by #92)

### 3. Compact agent evidence prompts (P1)

- **Why**: Directly addresses the highest-impact operational pain (slow turns). Reduces token budget pressure on the shared exo endpoint.
- **Files**: `services/research-orchestrator/app/opencode_runtime.py:307-311` (prompt loading), `services/research-orchestrator/app/engine.py:514-708` (context assembly), `services/research-orchestrator/prompts/honeydew.md` and `prompts/beaker.md` (agent system prompts)
- **Issue**: #93

### 4. Expose structured run-turn inspection endpoint (P1)

- **Why**: Currently only the editable Discord thread message is visible. Operators need read-only access to complete turn history, context packets, and agent outputs without scraping Discord.
- **Files**: `services/research-orchestrator/app/main.py` (new GET endpoint), `services/research-orchestrator/app/storage.py` (query assembly), `services/research-orchestrator/app/schemas.py` (response model)
- **Issue**: #95

### 5. Add Discord run status and discovery commands (P1)

- **Why**: Operators have no way to list active runs, check status, or discover available commands from Discord. The thread message is the only surface.
- **Files**: `services/research-orchestrator/app/discord_controls.py` (new slash commands), `services/research-orchestrator/app/discord_adapter.py` (rendering), `services/research-orchestrator/app/main.py` (command registration)
- **Issue**: #94

---

*File citations reference `cluster-config/` root. All claims verified against committed code, not live cluster state. Legacy classification per `AGENTS.md:90-97` and `docs/glasslab-v2/current/system-map-2026-07.md`.*
