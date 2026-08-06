# ADR 0002: Hermes Agent Runtime Pilot

## Status

Proposed

## Context

The research orchestrator currently starts one OpenCode process for Honeydew
and one for Beaker. OpenCode supplies each agent's inner model/tool loop, while
Glasslab owns the durable scientific workflow, approvals, evaluation-contract
integrity, cluster execution, artifacts, and Discord projection.

Hermes Agent now exposes documented control-plane integration points that make
it a credible alternative inner runtime:

- a bearer-authenticated Runs API with submission, status polling, SSE events,
  and stop control
- persisted session resources and session correlation
- custom OpenAI-compatible model providers
- profile-scoped configuration, history, memory, skills, and state
- an explicit terminal working directory
- per-platform toolsets and unconditional command deny rules

References:

- [Hermes API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/)
- [Hermes profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/)
- [Hermes configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/)
- [Hermes security](https://hermes-agent.nousresearch.com/docs/user-guide/security/)

Those capabilities may remove custom OpenCode-specific lifecycle and protocol
code. They do not replace Glasslab's scientific workflow semantics.

## Decision

Add an experimental `HermesProcessRuntime` behind the existing `AgentRuntime`
interface. Keep `opencode` as the deployment default.

The pilot launches one loopback-only Hermes gateway process per run and agent.
Each process receives:

- a distinct `HERMES_HOME`
- a distinct Hermes session ID and state database
- Honeydew's or Beaker's existing system prompt
- `terminal.cwd` fixed to that agent's existing Git worktree
- profile-scoped `HOME` for child tools
- an empty bundled-skill catalog
- memory, web, browser, delegation, cron, messaging, and skill toolsets disabled
- only the file and terminal toolsets enabled for the API-server platform
- unconditional command denials for Kubernetes, SSH, container engines, Git
  push, PR creation, and secret-oriented commands
- `HERMES_WRITE_SAFE_ROOT` fixed to the agent worktree
- the existing exo OpenAI-compatible endpoint and Qwen model

The adapter uses only Hermes's documented HTTP API:

```text
GET  /health
GET  /v1/capabilities
POST /api/sessions
GET  /api/sessions/{session_id}
POST /v1/runs
GET  /v1/runs/{run_id}
POST /v1/runs/{run_id}/stop
```

Hermes output is still validated independently as `AgentTurnResult`. Agent
recommendations do not advance Glasslab state and agent prose does not prove a
job or artifact exists.

## Non-Decision

This ADR does not approve replacing:

- the Glasslab state machine or append-only events
- protocol, execution, contract-promotion, or report approvals
- immutable evaluation contracts
- `workflow-api` or deterministic Kubernetes rendering
- artifact checksums and authoritative job records
- the Discord command and approval adapter

Hermes's own scheduler, messaging gateway, memory, skills, delegation, and
approval system remain disabled during the pilot. Enabling those would create
overlapping sources of truth and requires a separate decision.

## Security Boundary

Hermes documents its command deny rules and write-safe root as guardrails, not
a sandbox against an adversarial process. The initial adapter has process and
profile separation comparable to the current OpenCode integration, but the
process still runs in the orchestrator pod.

The Hermes backend must not become the live default until a deployment adds:

- a reviewed and digest-pinned Hermes build
- no Kubernetes service-account token in the runtime container
- a read-only evaluation-contract mount
- only the intended worktree as writable storage
- blocked cluster-admin, SSH, registry, and secret network paths
- a verified termination path for runtime and child processes

Pod- or container-level separation remains the target if Hermes wins the
functional pilot.

## Pilot Gates

The first comparison runs the same disposable task through OpenCode and Hermes.
Hermes is retained only if all gates pass:

| Gate | Evidence |
| --- | --- |
| Structured output | All required turn kinds validate without manual repair beyond the configured bounded retry. |
| Workspace containment | Honeydew and Beaker cannot read or mutate each other's worktrees or the contract source. |
| Tool policy | Raw Kubernetes, SSH, Git push, registry, secret, web, memory, skill, cron, and delegation actions are unavailable or denied. |
| Session recovery | A restarted gateway reconnects to the recorded session without repeating completed work. |
| Cancellation | Glasslab pause/cancel stops the active Hermes run and its child processes. |
| Observability | Hermes lifecycle and tool events can be normalized without making raw Hermes event names permanent Glasslab API. |
| Model compatibility | The current exo Qwen endpoint performs file edits, local tests, and structured completion reliably. |
| Performance | Wall time, input/output tokens, repair count, tool calls, and failure rate are recorded for both runtimes. |
| Scientific parity | The same orchestrator approvals, contract digest, jobs, artifacts, evaluation, and final acceptance remain authoritative. |

## Current Implementation State

Implemented in the pilot PR:

- explicit `agent_runtime_backend` selection
- per-run/per-agent profile and workspace configuration
- Runs API submission and polling
- persisted session lookup/creation
- stop-based abort
- bounded JSON parsing and schema validation
- mocked adapter, cancellation, selection, and isolation tests

Not yet implemented or tested:

- Hermes in the orchestrator image
- a digest-pinned Hermes version
- live exo/Qwen compatibility
- SSE event normalization
- run-approval event rejection through the live API
- restart and child-process recovery against a real Hermes gateway
- container-level runtime separation
- comparative latency and token measurements

## Rollout And Rollback

The checked deployment remains:

```text
GLASSLAB_ORCHESTRATOR_AGENT_RUNTIME_BACKEND=opencode
```

No live rollout should select `hermes` until the pilot image and all security
prerequisites are reviewed. Rollback is the same configuration switch followed
by an orchestrator rollout; durable Glasslab run, event, action, job, and
artifact records are runtime-independent.

## Consequences

- Runtime replacement can be evaluated without rewriting the research engine.
- Hermes API changes are contained in one adapter.
- The repository gains temporary dual-runtime code during evaluation.
- Hermes does not solve current workflow defects automatically; those remain
  Glasslab issues.
- A favorable pilot leads to a separate acceptance ADR and removal plan for
  OpenCode. An unfavorable pilot removes the adapter and closes the experiment.
