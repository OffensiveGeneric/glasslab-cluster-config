# Glasslab Research Orchestrator

Status: deployed as a single-replica MVP. The complete workflow is covered with
mocked OpenCode and cluster adapters. OpenCode against the two-node exo model,
Discord threads and role-gated controls, restart recovery, and live Kubernetes
deployment were tested on 2026-07-29. Three imported ML benchmark task types
now have bounded CPU/GPU workload definitions and immutable evaluator contracts;
their live end-to-end execution status is recorded below.

## Purpose

The research orchestrator coordinates two isolated research agents around the
existing bounded execution plane:

```text
 human / Discord / HTTP
           |
           v
 +-----------------------+
 | research-orchestrator |
 | state, policy, events |
 +----+-------------+----+
      |             |
      v             v
 Honeydew        Beaker
 OpenCode        OpenCode
 runtime         runtime
      |             |
      +------+------+
             |
             v
      structured actions
             |
             v
        workflow-api
             |
             v
     approved runner Jobs
             |
             v
  artifacts + evaluation output
```

OpenCode is the inner runtime. It performs each agent's model call, local tool
loop, file changes, and structured response. The orchestrator is the outer
scientific workflow. It owns turn-taking, approvals, durable state, privileged
actions, evidence, interruption, and recovery.

This separation avoids another home-grown model tool loop and prevents model
prose from being confused with an authoritative action result.

## Division Of Labor

Honeydew owns research methodology and synthesis. It drafts `program.md`,
reviews Beaker's proposed implementation and matrix, checks evaluation output,
and writes `report.md`. Only Honeydew may draft the protocol. It has no cluster
credentials and cannot change Beaker's worktree.

Beaker owns implementation and experiment analysis. It edits its isolated
worktree, runs bounded local checks, and proposes normalized experiment
matrices. It cannot run `kubectl`, use SSH, push Git changes, read secrets, or
publish artifacts.

The evaluation contract is repository-controlled and immutable to both agents.
It fixes the evaluator entry point, schemas, required artifacts, resource
limits, and optional digest-pinned image.

When an approved protocol requires a harness that is not installed, Beaker may
draft a contract candidate in its isolated worktree. The orchestrator validates
and seals it, Honeydew reviews the sealed read-only copy, and a Discord
administrator must approve promotion. Neither agent can write the trusted
catalog.

The orchestrator alone validates structured outputs, classifies actions,
performs state transitions, expands approved matrices, and delegates jobs to
the bounded cluster execution service.

## State Machine

The implemented states are:

```text
CREATED -> PREPARING -> HONEYDEW_DRAFTING_PROTOCOL
  -> AWAITING_PROTOCOL_APPROVAL
  -> BEAKER_DRAFTING_CONTRACT -> HONEYDEW_REVIEWING_CONTRACT
  -> AWAITING_CONTRACT_PROMOTION
  -> BEAKER_IMPLEMENTING -> HONEYDEW_REVIEWING
  -> BEAKER_REVISING (when requested)
  -> AWAITING_EXECUTION_APPROVAL
  -> JOB_QUEUED -> JOB_RUNNING
  -> BEAKER_ANALYZING -> HONEYDEW_VERIFYING
  -> HONEYDEW_WRITING_REPORT
  -> AWAITING_FINAL_ACCEPTANCE -> COMPLETE
```

`PAUSED`, `FAILED`, `CANCELLED`, and `TIMED_OUT` are explicit terminal or
control states. Transitions are validated in code. The agent may recommend a
next state but cannot perform the transition.

A failed Kubernetes job is stored as evidence and normally returns the run to
Beaker for analysis. It does not automatically fail the research run.

## Durable Records

The service stores runs, turns, actions, jobs, artifacts, and append-only events
in SQLite with WAL enabled. Each event receives a monotonically increasing
per-run sequence inside the same transaction as its state change.

The deployment is deliberately fixed at one replica. SQLite is placed on the
shared artifacts PVC. PostgreSQL is the expected next storage step before
horizontal scaling.

Normalized event names form the stable external contract. Raw OpenCode event
names are translated into events such as `agent.tool_started`,
`agent.turn_completed`, `action.proposed`, `job.completed`, and
`artifact.recorded`.

## Workspaces And OpenCode

Each run has this layout:

```text
runs/<run-id>/
  protocol/program.md
  beaker-worktree/
  honeydew-worktree/
  shared-artifacts/
  reports/
  events/
```

The worktree manager creates two detached Git worktrees from the one approved
repository. The approved protocol is copied read-only into each worktree.
Artifacts are copied through path-containment checks.

The OpenCode adapter starts one authenticated `opencode serve` child process
per agent. Each process receives a separate workspace, XDG configuration and
data directory, system prompt, permission configuration, server port, and
session ID. Sessions are recorded in the database and reconnected after an
orchestrator restart. Active turns have an explicit abort path.

The adapter uses the installed OpenCode HTTP API for server health, session
creation, structured message output, event streaming, and abort. Runtime event
names are not persisted directly.

The current deployment configuration points both runtimes at:

```text
http://192.168.1.18:52415/v1
mlx-community/Qwen3-Coder-Next-4bit
```

That is the model identifier exposed by the checked repository configuration.
The service does not assume that the label `qwen3-coder-next-70b` is accepted by
the endpoint. Confirm the served model list before changing this value.

## Structured Turns

Every completed turn is validated as an `AgentTurnResult`. It contains a kind,
summary, evidence-backed claims, structured requested actions, an optional
message to the other agent, a recommendation, and a completion flag.

Evidence references must use `artifact://`, `git://`, or `event://`. A turn
cannot establish that a job ran. Only persisted job and artifact records can do
that.

## Evaluation Integrity

Contracts live under
`services/research-orchestrator/evaluation-contracts/<id>/<version>`.
Resolution verifies:

- the declared ID and version
- input and output schema files
- the fixed evaluation entry point
- required artifacts and resource ceilings
- a SHA-256 digest over all contract content
- absence of symlinks

Generated contract candidates are bounded to safe text, Python, and JSON files,
syntax checked without executing candidate code, copied to a sealed directory,
and hashed by the orchestrator. The sealed bundle is then copied read-only into
Honeydew's workspace. Promotion installs that exact digest under:

```text
/mnt/artifacts/research-orchestrator/trusted-contracts/bundles/<id>/<version>
```

and atomically updates the shared trusted catalog. A protocol remains blocked
from experiment submission until its evaluator type, primary metric,
direction, required artifacts, and resource ceiling match the installed
contract.

Job proposals are recursively rejected when they attempt to supply evaluator
paths, contract mounts, contract files, entry-point overrides, or contract
digests. The deterministic Kubernetes renderer uses a digest-pinned init image,
copies the contract to an `emptyDir`, and mounts it read-only into the runner.

The authoritative `workflow-api` submission path independently resolves the
requested ID, version, and digest against its trusted contract catalog. For a
promoted shared bundle it independently re-hashes the content and descriptor,
then mounts the exact PVC subpath read-only. Image-backed contracts continue to
use a digest-pinned init image and read-only `emptyDir`. In either case it
replaces the runner command with the trusted wrapper. The wrapper executes the
registry-approved experiment entry point first and then the fixed evaluator.

The included example contract and image digest are test fixtures. Three
repository-controlled benchmark contracts are installed into the trusted
catalog at startup after checksum verification. Agent-generated contracts
still require Honeydew and human promotion approval. Unknown, changed, or
mismatched bundles fail closed.

## Imported ML Benchmarks

The orchestrator accepts these exact task archive names:

| Archive | Task ID | Execution |
|---|---|---|
| `ML_Benchmark_Adult_Income.zip` | `adult-income` | bounded CPU |
| `ML_Benchmark_Wine_Clustering.zip` | `wine-clustering` | bounded CPU |
| `ML_Benchmark_FashionMNIST_Contrastive.zip` | `fashion-mnist-contrastive` | one GPU |

The archive is an immutable research-task input, not executable code. Import
requires exactly one `problem.md` and one `eval_agent_prompt.md`, rejects
links/path traversal/oversized input, computes SHA-256, and stores a read-only
normalized copy. Dataset import is separate and fail-closed: the task cannot be
imported until its canonical datasets are staged and listed with digests in the
shared catalog.

Beaker writes runnable code only under
`benchmark-workspace/<task-id>/`. At approved submission time the orchestrator
creates a deterministic `source.zip`, sends task/source/dataset digest
references to `workflow-api`, and selects a fixed workload, image, resources,
command, and evaluation contract. The model cannot provide a Kubernetes
manifest, evaluator path, arbitrary image, or dataset path.

Start from Discord:

```text
/benchmark-start archive:<attach one supported ZIP>
```

Or use HTTP:

```bash
curl -fsS -X POST http://127.0.0.1:8080/task-bundles/import \
  -H "X-Glasslab-Operator-Token: $TOKEN" \
  -F "archive=@$HOME/Downloads/ML_Benchmark_Adult_Income.zip"

curl -fsS -X POST http://127.0.0.1:8080/runs \
  -H "X-Glasslab-Operator-Token: $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"objective":"Complete the imported Adult benchmark.","task_id":"adult-income"}'
```

Stage or refresh canonical datasets from `.44`:

```bash
./scripts/stage-ml-benchmark-datasets.sh
```

This downloads the official Adult and Wine files plus the four official
Fashion-MNIST IDX gzip files, verifies dataset sizes/headers, creates one
deterministic Fashion-MNIST archive, and writes the digest catalog to the
shared artifacts PVC.

## Actions And Jobs

Policy is deterministic:

| Action | Decision |
|---|---|
| Isolated reads, edits, and local tests | automatic |
| Experiment-branch commit | automatic and audited |
| Protocol update | Honeydew only |
| Evaluation-contract modification | denied |
| Draft evaluation-contract candidate | Beaker only |
| Promote sealed evaluation contract | Honeydew review and human approval |
| Small validation job | Honeydew approval |
| GPU job | Honeydew and human approval |
| Git push, PR, or publication | human approval |
| Secret read or shared-resource deletion | denied |

Images, CPU, memory, GPU, matrix size, parallelism, namespace, and contract
integrity are checked before submission. Matrix expansion is canonical and
deterministic across variants and seeds. Every expanded job receives a stable
idempotency key.

Before an experiment matrix can reach human approval, deterministic preflight
also verifies that its base configuration exists in Beaker's worktree, the
evaluation-contract digest is unchanged, and every requested resource fits the
contract's own ceilings. Honeydew's structured approval cannot bypass these
checks.

Approval and execution are separate audited facts. If an approved action cannot
execute, the orchestrator records `action.execution_failed` with the error,
authoritative job and artifact counts, retry classification, resulting safe
state, and next step. A deterministic matrix failure is marked
`execution_failed` and returned to Beaker for revision. A transient runtime or
infrastructure failure preserves the approval and pauses the run for
reconciliation and explicit resume.

The `workflow-api` adapter uses the existing approved workload API and never
passes Kubernetes credentials to an agent. `workflow-api` now owns the trusted
evaluation-contract catalog and read-only wrapper mount. It does not yet
provide a remote idempotency-header contract or a confirmed cancellation
endpoint. The orchestrator preserves local idempotency, but a crash between a
successful remote submission and local persistence remains a live-integration
gap.

## Long Jobs And Recovery

Agent turns end before submission. While jobs run, OpenCode is idle and the
watcher reconciles authoritative job state. Completion records exit details and
artifacts before beginning a new agent turn.

At startup the service:

1. marks interrupted active turns for audit,
2. reloads nonterminal runs,
3. reconnects recorded OpenCode sessions when possible,
4. reconciles `JOB_QUEUED` and `JOB_RUNNING` jobs, and
5. advances workflows only after authoritative evidence is stored.

Cancellation aborts active OpenCode turns and requests cancellation for every
nonterminal job. Prior events are retained.

## Discord

Discord is an optional projection. One run maps to one thread, with semantic
Honeydew, Beaker, and Orchestrator messages and one editable status message.
Messages are rendered from persisted events after transaction commit. No
token-by-token output is posted, and Discord history is never used as memory.

The guild-scoped `/research-start objective:...` command is the human front
door. It invokes the same authoritative `create_run` engine method as the HTTP
API, then creates the run thread. The command is role-gated using the same
configured Discord control policy as approvals. The HTTP endpoint remains an
internal automation and recovery interface; operators are not expected to
construct it by hand for normal work.

The bot creates public threads and owns the editable status message. An
optional channel webhook posts semantic events with per-message Honeydew,
Beaker, and Orchestrator identities. Agent turn messages include the explicit
`message_to_other_agent` handoff stored in the authoritative event. The
webhook cannot approve actions or alter workflow state.

Approval messages are decision briefs rather than bare action IDs. They state
the research objective, the artifact or experiment scope under review, per-job
resources and concurrency where applicable, the evaluation contract, the gate
reason, and exactly what approval authorizes. A matrix proposal is first posted
without controls while Honeydew reviews it. Approve and Reject controls appear
only after deterministic preflight and Honeydew methodology approval succeed.
Post-approval execution failures are posted publicly in the run thread from the
persisted failure event; an ephemeral interaction response is not the only
failure signal.

Honeydew's protocol turn also returns a schema-validated logical evaluation
contract proposal: evaluator type, primary metric, direction, minimum effect,
guardrails, required artifacts, budget mode, resource ceilings, and rationale.
The orchestrator stores it as a checksummed artifact and shows it in the
protocol approval brief. The proposal cannot contain executable paths, images,
commands, or digests. Those remain in the repository-controlled immutable
harness. The brief explicitly reports whether the proposal is compatible with
the currently bound harness or requires a new trusted harness.

The bot requires only View Channel, Send Messages, Read Message History,
Create Public Threads, and Send Messages in Threads on the configured channel.
It does not require Administrator. When controls are enabled, the bot maintains
an outbound Gateway connection and posts Approve and Reject buttons on pending
actions. No public callback ingress is required. Each interaction is checked
against the configured guild, run thread, pending action, and immutable admin
role or user IDs before invoking the same authoritative engine methods as the
HTTP API. The Discord user ID and display name are stored as the reviewer.
Buttons acknowledge immediately; long agent work continues asynchronously.

The bot token and webhook URL belong in the ignored local Kubernetes Secret.
Application, guild, channel, and approval-role IDs are non-secret deployment
configuration. Glasslab currently authorizes the `Mystic Arts Masters` role
by ID. Discord role membership is therefore the operational approval policy.

## HTTP API

The service provides:

```text
POST /runs
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/events
GET  /runs/{run_id}/events/stream
GET  /runs/{run_id}/artifacts
POST /runs/{run_id}/pause
POST /runs/{run_id}/resume
POST /runs/{run_id}/cancel
GET  /actions/{action_id}
POST /actions/{action_id}/approve
POST /actions/{action_id}/reject
GET  /health
GET  /ready
```

Deployment requires `X-Glasslab-Operator-Token` on all state-changing
endpoints. Health, readiness, run reads, events, artifacts, and SSE remain
read-only. Local development leaves this check disabled unless
`GLASSLAB_ORCHESTRATOR_REQUIRE_OPERATOR_AUTH=true`.

Normal Discord usage is:

```text
/research-start objective: Compare naive and semi-hard triplet mining on unseen CIFAR-100 classes.
```

Imported benchmark usage is `/benchmark-start` with a supported ZIP
attachment. Both commands are restricted to the configured channel and
Discord administrator role.

## Local Development

```bash
cd services/research-orchestrator
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -p no:cacheprovider -q
PYTHONPATH=. python3 -m app.smoke
```

The repository smoke wrapper is:

```bash
./scripts/smoke-test-research-orchestrator.sh
```

It needs no GPU, Qwen endpoint, Kubernetes access, or Discord token. It
demonstrates objective, protocol approval, implementation, review, fake job
approval and completion, analysis, verification, report, final acceptance, and
`COMPLETE`.

Configuration is documented in
`services/research-orchestrator/.env.example`. Never commit the Discord token or
other live credentials.

## Deployment

The image is built from `services/research-orchestrator/Dockerfile`. Manifests
are under `kubeadm/glasslab-v2/research-orchestrator` and are included by
`scripts/deploy-glasslab-v2.sh`.

The manifest enforces one replica, disables service-account token mounting,
runs as a non-root user, and stores SQLite and workspaces on
`glasslab-shared-artifacts`. An init container maintains the approved
repository checkout.

Before deployment:

1. publish the orchestrator image and pin the desired tag or digest,
2. publish both benchmark workspace runner images when benchmark support changes,
3. verify the Qwen endpoint and exact model ID from the target node,
4. configure the published contract in the workflow-api trusted catalog,
5. validate workflow submission, status, artifacts, idempotency, and cancel,
6. create a local Discord secret only when Discord is enabled, and
7. deploy from the canonical checkout on `.44`, and
8. run `scripts/stage-ml-benchmark-datasets.sh`.

## Legacy Relationship

The Titanic agent stack remains under `services/agent-api`, `services/runner`,
and `kubeadm/agent-stack`. It is preserved as v1 reference material.

The orchestrator does not copy its Titanic-specific intent parser, SQLite
schema, or direct Kubernetes submission model. It reuses the lessons and the
bounded execution boundary represented by `workflow-api` and
`research-workspace-runner`. The old stack can continue to run during migration.

## Validation Status

Implemented:

- state machine, durable records, ordered events, approvals, and recovery
- isolated worktree and OpenCode runtime adapters
- structured turn validation and normalized runtime events
- contract digest checks and read-only job rendering
- policy, quotas, matrix expansion, fake and workflow-api cluster adapters
- HTTP API, SSE, Discord renderer, manifests, and configuration

Covered by mocks:

- the full Honeydew/Beaker workflow
- structured OpenCode turn completion and abort behavior
- parallel fake jobs, completion, failure evidence, and artifacts
- restart reconciliation and cancellation

Manually tested:

- OpenCode `1.4.6` headless health and session create/delete on this laptop
- the non-root service image build, OpenCode version, application import, and
  `/ready` response
- a real structured Honeydew turn through OpenCode `1.4.6` and the exo-served
  `mlx-community/Qwen3-Coder-Next-4bit` model from `.44`
- live Discord public-thread creation, editable status publication, and
  Honeydew/Beaker webhook identities in the configured guild and channel

Not yet tested:

- full Adult, Wine, or Fashion-MNIST benchmark completion on live GPUs/CPUs

## MVP Limitations

- one orchestrator replica and one active research run
- SQLite WAL rather than PostgreSQL
- one approved repository and fixed agent profiles
- one process per agent, not a separate pod or Unix identity
- no Git push, PR creation, arbitrary SSH, or raw Kubernetes access
- no autonomous literature subsystem
- deterministic benchmark gates validate required evidence and core invariants;
  Honeydew still performs the detailed rubric assessment

## Files

The implementation is contained in:

- `services/research-orchestrator/`
- the evaluation-contract enforcement path in `services/workflow-api/`
- `kubeadm/glasslab-v2/research-orchestrator/`
- `scripts/smoke-test-research-orchestrator.sh`
- `scripts/stage-ml-benchmark-datasets.sh`
- `docs/research-orchestrator.md`

CI, pre-push checks, deployment orchestration, and current documentation indexes
are updated to include the service.
