# Research Orchestrator Discord Operator Guide

Last verified: 2026-08-11

This is the operator reference for controlling a Glasslab research run through
Discord. It covers the exact slash-command surface, approval flow, pause/resume/
cancel behavior, where artifacts appear, what Discord does *not* expose, and
common recovery procedures. For the state machine and architecture, read
[`research-orchestrator.md`](research-orchestrator.md). For the concise
command-reference table and HTTP API, read
[`research-orchestrator-command-surface.md`](research-orchestrator-command-surface.md).

---

## 1. Available Slash Commands

All commands are guild-scoped to the configured Glasslab channel and an
approval role (`Mystic Arts Masters` in the live deployment) or an explicit
administrator allowlist
(`discord_controls.py:61-72`).

Commands registered at `discord_controls.py:257-409`:

### `/research-start objective:<text>`

- **Where**: main Glasslab channel only
  (`discord_controls.py:472-477`).
- **What**: Starts a question-driven research run. Honeydew drafts `program.md`
  and an evaluation-contract proposal.
- **Authorization**: guild admin role or explicit user ID
  (`discord_controls.py:465-471`).
- **Objective length**: 10–2000 characters
  (`discord_controls.py:271`).
- **Heavy work**: the engine call `create_run(RunCreateRequest(objective=objective))`
  runs in a worker thread so the gateway event loop is never blocked
  (`discord_controls.py:504-508`).
- **Follow-up**: a public thread named `research-<run_id[:8]>` is created in the
  channel, and the user receives the thread mention
  (`discord_controls.py:509-521`).

### `/task-start archive:<zip> [objective:<text>]`

- **Where**: main Glasslab channel only
  (`discord_controls.py:543-550`).
- **What**: Compiles the task ZIP into a `glasslab-task-spec-v1`
  (Honeydew task-compiler turn), runs deterministic preflight, and starts the
  run only when all required inputs are ready
  (`discord_controls.py:175-194`; `engine.py:180-283`).
- **Archive limit**: 16 MiB (`engine.py:554` — `MAX_ARCHIVE_BYTES`).
- **Authorization**: same role and channel gating as `/research-start`.
- **Re-import of identical bytes**: no-op; keyed by SHA-256 of the archive
  (`engine.py:303-308`).

### `/benchmark-start archive:<zip> [objective:<text>]`

- **What**: Compatibility alias for `/task-start`. Internally calls the same
  `_on_benchmark_start` handler; the two command decorators share the callback
  (`discord_controls.py:278-316`, `discord_controls.py:216`).
- **Do not** build new integrations around this name. Use `/task-start`.

### `/dataset-upload dataset:<file> name:<name> [role:<role>] [contains_labels:<bool>]`

- **Where**: main Glasslab channel only
  (`discord_controls.py:712-717`).
- **What**: Stores a file immutably under the shared artifact mount, registers
  the SHA-256 digest in SQLite, and returns a `glasslab-dataset://<sha256>`
  reference
  (`discord_controls.py:146-165`).
- **Size ceiling**: configured per-file `maximum_dataset_upload_bytes`
  (`discord_controls.py:720-723`). Discord uploads are also limited to 100 MiB
  by service policy.
- **Use**: put the returned URI in `problem.md` or the research objective before
  starting a task. The orchestrator resolves the reference to a read-only
  shared-storage object and verifies the digest during preflight.

### `/research-pause [run_id:<id>] [reason:<text>]`

- **Where**: run thread (no `run_id` required) or main channel (with `run_id`)
  (`discord_controls.py:586-617`).
- **What**: Aborts any active OpenCode turns for both agents, accumulates
  elapsed active runtime, records the prior state as `resume_state`, and
  transitions the run to `PAUSED`
  (`engine.py:3581-3620`).
- **Reason length**: 3–500 characters
  (`discord_controls.py:391`).

### `/research-resume [run_id:<id>] [reason:<text>]`

- **Where**: same channel rules as pause.
- **What**: Rotates any stale failed session, transitions the run to the stored
  `resume_state`, restarts the active-runtime clock, and calls `_recover_run()`
  which dispatches to the correct phase
  (`engine.py:3622-3663`).
- If recovery itself fails, the run is re-paused with the error recorded
  (`engine.py:3656-3662`).

### `/research-cancel [run_id:<id>] [reason:<text>]`

- **Where**: same channel rules as pause.
- **What**: Aborts active OpenCode turns, walks every `QUEUED`/`SUBMITTING`/
  `RUNNING`/`UNKNOWN` job and requests cancellation through the cluster adapter,
  marks each job `CANCELLED`, and transitions the run to `CANCELLED`
  (`engine.py:3754-3811`).
- **Does not** wait for the advancement lock — cancellation must interrupt an
  active model turn
  (`engine.py:3761`).

### `/research-artifacts [run_id:<id>] [include_source:<bool>]`

- **Where**: run thread (no `run_id` required) or main channel (with `run_id`).
- **What**: Builds a digest-verified ZIP of the latest run-level artifacts and
  successful-job outputs. Each ZIP contains `artifact-manifest.json` with the
  original URI, digest, job ID, and archive path for every delivered file
  (`discord_controls.py:197-212`).
- **Default bundle**: protocol, report, analysis notebook, metrics, evaluation
  output, tables, manifests, and logs from successful jobs. Failed-job files and
  duplicate superseded run-level artifacts are excluded.
- **`include_source:true`**: includes frozen source and task ZIP files.
- **Ceiling**: 24 MiB by default (`discord_controls.py:232`).

---

## 2. Approval Flow

### Gates and their states

Four approval gates exist, each corresponding to a `RunState` where the run
pauses for human input:

1. **Protocol approval** — `AWAITING_PROTOCOL_APPROVAL`
   - After Honeydew drafts `program.md` and the evaluation-contract proposal,
     a human action of type `approve_protocol` is created
     (`engine.py:1473-1478`).
   - The brief describes the research objective, protocol version, SHA-256, and
     Honeydew's contract proposal
     (`discord_adapter.py:80-143`).

2. **Contract promotion** — `AWAITING_CONTRACT_PROMOTION`
   - After Beaker drafts a candidate, the orchestrator seals/validates it,
     Honeydew reviews it, and a human `propose_evaluation_contract` action is
     surfaced
     (`engine.py:2013-2022`).
   - Honeydew review must succeed (`done=true`) before human controls appear;
     if Honeydew rejects, the run returns to Beaker for redrafting
     (`engine.py:1972-1993`).

3. **Execution approval** — `AWAITING_EXECUTION_APPROVAL`
   - After Beaker proposes the experiment matrix, deterministic preflight
     validates it, Honeydew performs methodology review and approves, and a
     human `submit_experiment_matrix` action is surfaced.
   - The brief reports job count, variant names, seeds, per-job resources,
     concurrency ceiling, and preflight results
     (`discord_adapter.py:177-247`).

4. **Final report acceptance** — `AWAITING_FINAL_ACCEPTANCE`
   - After job completion, Beaker analysis, and Honeydew verification, Honeydew
     writes `report.md` and a human `accept_final_report` action is created
     (`engine.py:3574-3579`).

### Buttons and what they render

Approve and Reject are Discord message buttons, not slash commands
(`discord_controls.py:81-82` — operation whitelist: `approve` or `reject` only).

Controls are rendered only when the action is in `approval_status=pending` and
either the policy classification is not `HONEYDEW_AND_HUMAN_APPROVAL` or
Honeydew has already approved
(`discord_adapter.py:344-347`; `engine.py:880-888`).

Button labels vary by action type
(`discord_adapter.py:43-59`):

| Action type | Approve label |
|---|---|
| `approve_protocol` | `Approve protocol` |
| `accept_final_report` | `Accept report` |
| `submit_experiment_matrix` | `Approve N jobs` (uses `len(variants) * len(seeds)`) |
| `propose_evaluation_contract` | `Promote contract` |

The Reject button always says `Reject` and opens a modal that requires 5–1000
characters of revision feedback
(`discord_controls.py:978-1009`).

### What approve does

All approve calls flow through `engine.approve_action()` (`engine.py:1508-1552`):

- Validates the action is `PENDING` (or `APPROVED` — treated as recovery retry).
- For `HONEYDEW_AND_HUMAN_APPROVAL` actions, checks that `honeydew_approved`
  is set (`engine.py:1529-1534`).
- Records the Discord reviewer identity (`discord:<user_id>:<display_name>`)
  through the `DiscordControlActor.reviewer` property
  (`discord_controls.py:42-46`).
- Calls `_resume_approved_action()` which dispatches by action type
  (`engine.py:1628-1663`):

| Action type | Immediate effect |
|---|---|
| `approve_protocol` | Freezes protocol read-only, transitions to `BEAKER_PLANNING` (or `BEAKER_DRAFTING_CONTRACT` if the proposal is incompatible) |
| `propose_evaluation_contract` | Promotes the sealed candidate into the trusted contract catalog, rebinds the run digest, transitions to `BEAKER_PLANNING` |
| `submit_experiment_matrix` | Expands the matrix deterministically and submits jobs through `workflow-api`, transitions to `JOB_QUEUED` |
| `accept_final_report` | Transitions to `COMPLETE`, emits `run.completed` |

- If execution of the approved action fails (e.g. matrix expansion error), the
  orchestrator records `action.execution_failed`. A deterministic matrix failure
  (no jobs created yet) transitions to `BEAKER_REVISING` for automatic revision.
  Any other failure pauses the run for operator reconciliation
  (`engine.py:1554-1626`).

### What reject does

All reject calls flow through `engine.reject_action()` (`engine.py:1665-1708`):

- Validates the action is `PENDING` (or `REJECTED` — treated as recovery retry
  that re-enters the rejection path).
- Records the reviewer and the required revision feedback text.
- Calls `_resume_rejected_action()` which dispatches by action type
  (`engine.py:1710-1750`):

| Action type | Result |
|---|---|
| `approve_protocol` | Returns to `HONEYDEW_DRAFTING_PROTOCOL` with rejection feedback |
| `submit_experiment_matrix` | Returns to `BEAKER_REVISING` with rejection feedback |
| `accept_final_report` | Returns to `HONEYDEW_WRITING_REPORT` with rejection feedback |
| `propose_evaluation_contract` | Returns to `BEAKER_DRAFTING_CONTRACT` with rejection feedback |

Rejection feedback is stored as the action's `reason` field and passed to the
responsible agent as structured feedback. An approval is not evidence that
execution succeeded; job and artifact records remain authoritative.

---

## 3. Pause / Resume / Cancel Behavior

### Pause (`/research-pause`)

`engine.pause_run()` at `engine.py:3581-3620`:

1. **Does not** acquire the advancement lock — it must interrupt a model turn
   that holds that lock
   (`engine.py:3588`).
2. Calls `_abort_agent_turns()` which sends abort signals to both Honeydew's
   and Beaker's OpenCode sessions via their runtime IDs
   (`engine.py:3740-3752`).
3. Accumulates elapsed active runtime:
   `active_runtime_seconds += (now - active_since)`
   (`engine.py:3595-3600`).
4. Sets `resume_state = current_state` so resume knows which phase to restore
   (`engine.py:3605`).
5. Sets `active_since = None` — the active-runtime clock stops
   (`engine.py:3607`).
6. Transitions to `PAUSED` and emits `run.paused` event
   (`engine.py:3601-3619`).
7. The Discord status message updates to "Run paused"
   (`discord_adapter.py:453-458`).

**Effect on agents**: any in-progress model turn is aborted. The worktree is
preserved unchanged. The agent session is NOT immediately rotated — rotation
happens on resume if needed.

**Effect on budgets**: turn count is preserved. Active runtime is frozen.

**Effect on cluster jobs**: none. Running Kubernetes jobs are NOT cancelled by
pause. They continue to execute and the watcher records their completion as
normal.

### Resume (`/research-resume`)

`engine.resume_run()` at `engine.py:3622-3663`:

1. Acquires the advancement lock
   (`engine.py:3629`).
2. Validates the run is `PAUSED` with a non-null `resume_state`
   (`engine.py:3631-3632`).
3. Calls `_rotate_failed_session_before_resume()`: if the latest failed turn for
   the target agent still references the active session ID, rotates that session
   (writes recovery checkpoint, clears session IDs, terminates the OpenCode
   process)
   (`engine.py:3665-3738`).
4. Transitions the run to `resume_state`, clears `resume_state` to `None`, and
   sets `active_since = utc_now()` (restarts the active-runtime clock)
   (`engine.py:3636-3643`).
5. Emits `run.resumed` event
   (`engine.py:3644-3653`).
6. Calls `_recover_run()` which dispatches to the correct phase method
   (e.g. `_draft_protocol`, `_beaker_implement`, `_analyze_results`, etc.)
   (`engine.py:3926-4064`).
7. If `_recover_run()` raises, the run is re-paused with the error
   (`engine.py:3656-3662`).

**Effect on agents**: a fresh OpenCode session is created if the previous
session was rotated. The recovery checkpoint (written to
`events/<agent>-recovery-checkpoint.json`) is injected as context into the fresh
session
(`engine.py:544-563`). The existing worktree is preserved and not reset.

**Effect on budgets**: turn count and total runtime continue from where they
were. The per-turn budget check (`_check_turn_budget`) runs at the next turn
boundary and may trigger `TIMED_OUT`
(`engine.py:384-414`).

**Effect on cluster jobs**: if the resume target is `JOB_QUEUED` or
`JOB_RUNNING`, `reconcile_run()` is called instead to reconcile authoritative
job state without submitting new work
(`engine.py:4048-4049`).

### Cancel (`/research-cancel`)

`engine.cancel_run()` at `engine.py:3754-3811`:

1. **Does not** acquire the advancement lock — it must interrupt an active
   model turn
   (`engine.py:3761`).
2. Aborts active OpenCode turns for both agents
   (`engine.py:3765`).
3. Iterates every `QUEUED`, `SUBMITTING`, `RUNNING`, and `UNKNOWN` job:
   - Calls `cluster.cancel(external_run_id)` for each job with an external ID
     (`engine.py:3776-3780`).
   - Marks each job `CANCELLED` in the local store with
     `exit_information.cancel_requested = true`
     (`engine.py:3781-3791`).
4. Transitions the run to `CANCELLED`
   (`engine.py:3792-3800`).
5. Emits `run.cancelled` event with any cancellation errors and the requesting
   actor/reason
   (`engine.py:3801-3811`).
6. `CANCELLED` is a terminal state. It **cannot** currently be resumed through
   `/research-resume`. Retry-from-terminal-checkpoint is a known missing
   capability.

**Effect on agents**: any in-progress turn is aborted. Prior events are retained
(`engine.py:3801-3811`).

**Effect on budgets**: all remaining budget is discarded.

**Effect on cluster jobs**: cancellation is best-effort. If `workflow-api` does
not support confirmed cancellation, the jobs may continue running. The
orchestrator does not wait for job termination before transitioning to
`CANCELLED`.

---

## 4. Where Artifacts and Reports Appear in Discord

### Thread structure

One research run maps to one public Discord thread named
`research-<first-8-chars-of-run-id>`
(`discord_adapter.py:537`).

Inside the thread, three message identities appear:

| Identity | Source | Example events |
|---|---|---|
| **Honeydew** | Webhook when `agent.source == 'honeydew'` | `agent.turn_completed` summaries, handoff messages to Beaker |
| **Beaker** | Webhook when `agent.source == 'beaker'` | `agent.turn_completed` summaries, handoff messages to Honeydew |
| **Orchestrator** | Webhook or bot message | Status changes, job lifecycle, approval/rejection, pauses |

(`discord_adapter.py:297-302`)

### Status message

One editable status message is pinned to the run thread. It is edited in place
(rather than reposted) for every state transition, so the status line does not
spam the thread
(`discord_adapter.py:609-619`; `discord_adapter.py:27-31`).

Status events include:
- `run.state_changed` → `"State: <from> -> <to>"`
  (`discord_adapter.py:313-318`)
- `run.paused`, `run.resumed`, `run.cancelled`, `run.completed`
  (`discord_adapter.py:448-458`)
- `run.failed` → includes the error cause
  (`discord_adapter.py:459-476`)

### Agent turn messages

When an agent turn completes, the `agent.turn_completed` event is rendered as a
message with the agent's identity and turn summary. If the structured output
includes `message_to_other_agent`, it is appended as `"**To <other agent>:** <handoff>"`
(`discord_adapter.py:319-328`).

### Approval briefs

Approval briefs are rendered as detailed decision messages from the action's
`approval_event_payload`. They include:
- Research objective
- What is under review (artifact URI, SHA-256, protocol version, etc.)
- Evaluation contract details
- The gate reason
- What approval authorizes
- For experiment matrices: job count, variant names, seeds, per-job resources,
  concurrency ceiling, and deterministic preflight results
(`discord_adapter.py:62-293`; `engine.py:873-999`).

### Report

When `report.created` fires, a Honeydew-identity message `"Report ready: <uri>"`
is posted
(`discord_adapter.py:443-447`).

### Artifact download

`/research-artifacts` returns a file attachment in an ephemeral reply. The
message shows `"Digest-verified artifact bundle for <run_id> (N files)."`
(`discord_controls.py:787-798`). This is **visible only to the requesting user**.

### Job lifecycle

Job events (`job.submitted`, `job.completed`, `job.failed`) post Orchestrator
messages with the job ID
(`discord_adapter.py:438-442`).

---

## 5. What Discord Does NOT Show

Discord is a transcript projection, not authoritative memory or state. The
following are NOT visible through the Discord interface:

### Events not rendered to Discord

The `DiscordRenderer.render()` method at `discord_adapter.py:304-476` produces
`None` for any event type it does not recognize. The following known event types
produce no Discord message:
- `agent.turn_started`
- `agent.output_rejected`
- `agent.output_repaired`
- `agent.file_repair_requested`
- `agent.file_repair_completed`
- `agent.session_rotated`
- `agent.context_attached`
- `agent.plan_created`
- `contract.proposal_bound`
- `contract.candidate_rejected`
- `contract.candidate_sealed`
- `contract.candidate_reviewed`
- `contract.promoted`
- `artifact.recorded`
- `methodology.*` (except those rendered through action events)
- `run.created` (rendered only as a brief Orchestrator message)
- `run.recovered`
- `run.recovery_failed`

These events exist ONLY in the append-only event database and are queryable
through the HTTP API (`GET /runs/{run_id}/events`).

### Raw OpenCode sessions, tokens, and tool calls

Discord renders the final structured turn summary and the `message_to_other_agent`
handoff. It does NOT show:
- Raw model prompts or completions
- Per-tool invocations (file reads, writes, shell commands)
- Token-by-token streaming output
- OpenCode's internal session data

The raw OpenCode storage lives in
`/mnt/artifacts/research-orchestrator/runs/<run-id>/runtime/<agent>/` and is
**inspectable only through `kubectl exec`** into the orchestrator pod. Discord
history is never used as memory
(`research-orchestrator.md:465`).

### Agent workspaces and worktrees

Discord does NOT provide access to:
- Beaker's worktree files
- Honeydew's worktree files
- The shared-artifacts directory
- The protocol frozen copy
- The recovery checkpoints

Use `kubectl exec` from the provisioner to inspect these. The HTTP API does not
expose a directory browser or raw file download endpoint for workspaces.

### List and status queries

There are no Discord slash commands to list runs or query status. The only
status indicator is the run thread's editable status message and the sequence of
events posted in the thread. The HTTP API (`GET /runs`, `GET /runs/{run_id}`)
is the authoritative query path.

### Rejection modal flow

When a user clicks Reject, a modal appears to collect revision feedback. This
modal is per-user ephemeral and its text is attached to the `action.rejected`
event as the `reason` field, which is then rendered in the thread. The modal
itself is not visible to other thread participants.

---

## 6. Common Recovery Procedures

### Stuck run (agent turn appears hung)

The 70B model endpoint may take up to a 30-minute deadline per turn. If an
agent turn appears stuck:

1. **Pause the run** from the thread:
   ```text
   /research-pause reason: Turn appears stalled; re-queuing.
   ```
   This aborts the active OpenCode session and preserves the worktree
   (`engine.py:3740-3752`).

2. **Resume the run**:
   ```text
   /research-resume reason: Recovery after stuck turn.
   ```
   Resume rotates any failed session, writes a recovery checkpoint, creates a
   fresh OpenCode session, injects the checkpoint, and continues from the
   unchanged worktree
   (`engine.py:3622-3663`, `engine.py:544-563`).

If the orchestrator process itself is unhealthy, the `recover()` method runs at
startup and handles both interrupted turns and state recovery
(`engine.py:3813-3890`).

### Timed-out run

`TIMED_OUT` occurs when:
- `turn_number >= maximum_turns` (`engine.py:389-395`)
- `active_runtime_seconds > maximum_runtime_seconds` (`engine.py:405-414`)

`TIMED_OUT` is a terminal state and **cannot currently be resumed** through
`/research-resume`. The workaround is to start a new run. Retry-from-terminal-
checkpoint is a documented missing capability.

Before starting a new run, verify:
1. The run's events through the HTTP API to understand which phase was reached.
2. Any completed jobs and artifacts through `GET /runs/{run_id}/artifacts`.
3. Download any useful results with `/research-artifacts` before the workspace
   PVC data is aged out.

### Agent looping (Honeydew/Beaker repeating the same turn)

If an agent repeatedly fails the same bounded phase (e.g. Honeydew
methodology review rejecting and Beaker revisiting indefinitely), the
orchestrator has built-in limits:

- **Methodology revision limit**: `GLASSLAB_ORCHESTRATOR_MAXIMUM_METHODOLOGY_REVISIONS`
  (default 2). Exceeding this limit at `BEAKER_REVISING` pauses the run and
  emits `methodology.human_resolution_requested` instead of consuming the
  remaining turn budget
  (`research-orchestrator.md:390-394`).
- **Contract-candidate rejection**: when the orchestrator rejects a candidate
  during deterministic validation, Beaker re-drafts with the failure as
  feedback. This retry chain is bounded by the per-run turn budget, which
  eventually transitions to `TIMED_OUT`
  (`engine.py:1881-1888`).

Manual intervention:
1. Pause the run.
2. Inspect the event log through the HTTP API to identify the loop pattern.
3. Consider starting a new run with a narrower objective or providing additional
   context.

### Approved action execution failed

Approved actions should post their execution failure publicly in the run thread
from the `action.execution_failed` event
(`discord_adapter.py:414-437`).

This event reports:
- The action type that failed
- The error message
- How many jobs and artifacts were already created
- The resulting run state
- The recommended next step

Two outcomes are possible (`engine.py:1569-1576`):

**Deterministic matrix failure** (no jobs created yet, `ValueError`):
- Run transitions to `BEAKER_REVISING` automatically
- Beaker receives the failure as feedback and revises the matrix
- No operator action required

**Any other failure** (jobs may have been partially created):
- Run is paused
- Operator must reconcile partial state before resuming
- Resume retries the authoritative action

### Cancelled / failed run with leftover cluster jobs

`/research-cancel` best-effort cancels active jobs through the cluster adapter,
but `workflow-api` may not support confirmed cancellation. If jobs remain
running after cancellation:

1. Check active jobs from the provisioner:
   ```bash
   ssh glasslab-provisioner
   sudo -n env KUBECONFIG=/home/glasslab/.kube/config \
     kubectl -n glasslab-v2 get jobs -o wide
   ```
2. Delete remaining jobs manually if needed.
3. Job deletion does not affect the orchestrator's recorded state — the local
   `CANCELLED` status is already persisted.

### Orchestrator restart during a run

At startup, `engine.recover()` (`engine.py:3813-3890`):
1. Backfills any local artifact records from the event log.
2. For each active run: marks `running` turns as interrupted.
3. Rotates any interrupted agent session (writes recovery checkpoint, creates
   fresh session on the next turn).
4. Calls `_recover_run()` which dispatches to the correct phase method based on
   the run's current state.

If recovery fails in an agent-active state, the run is paused with a recovery
error. If recovery fails in a non-agent state (e.g. awaiting approval), the run
fails.

After a restart, the watcher also reconciles `JOB_QUEUED` and `JOB_RUNNING` jobs
by querying `workflow-api` for authoritative status.

### Checking the authoritative state

When Discord is insufficient, query the HTTP API through a port-forward:

```bash
ssh -L 18080:127.0.0.1:18080 glasslab-provisioner \
  'sudo -n env KUBECONFIG=/home/glasslab/.kube/config \
   kubectl -n glasslab-v2 port-forward \
   svc/glasslab-research-orchestrator 18080:8080'
```

Then:
```bash
RUN=<run-id>
curl -fsS "http://127.0.0.1:18080/runs/$RUN" | jq
curl -fsS "http://127.0.0.1:18080/runs/$RUN/events" | jq
curl -fsS "http://127.0.0.1:18080/runs/$RUN/artifacts" | jq
curl -N "http://127.0.0.1:18080/runs/$RUN/events/stream"
```

Per-run durable files are mounted in the orchestrator pod at:
```text
/mnt/artifacts/research-orchestrator/runs/<run-id>/
  protocol/
  beaker-worktree/
  honeydew-worktree/
  shared-artifacts/
  reports/
  events/
  runtime/beaker/
  runtime/honeydew/
```

Inspect workspaces through `kubectl exec` rather than assuming the path exists
on the provisioner's local filesystem.
