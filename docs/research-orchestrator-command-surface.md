# Research Orchestrator Command Surface

Last verified: 2026-07-29

This is the concise operator and contributor reference for the Honeydew/Beaker
research workflow. The database and append-only event log are authoritative.
Discord is the normal human interface and a projection of that state.

## Discord Commands

Commands are guild-scoped and restricted to the configured Glasslab channel
and approval role or explicit administrator allowlist.

| Command | Where | Effect |
| --- | --- | --- |
| `/research-start objective:<text>` | Main Glasslab channel | Starts a question-driven run. Honeydew drafts the protocol and evaluation contract proposal. |
| `/task-start archive:<zip> [objective:<text>]` | Main Glasslab channel | Compiles an arbitrary task archive, performs preflight, and starts the run only when required inputs are ready. |
| `/benchmark-start archive:<zip> [objective:<text>]` | Main Glasslab channel | Compatibility alias for `/task-start`; do not build new integrations around this name. |
| `/dataset-upload dataset:<file> name:<name> [role:<role>] [contains_labels:<bool>]` | Main Glasslab channel | Stores a file immutably and returns a checksum-addressed `glasslab-dataset://` reference. |
| `/research-pause [run_id:<id>] [reason:<text>]` | Run thread, or main channel with `run_id` | Aborts an active model turn, preserves state, and records where to resume. |
| `/research-resume [run_id:<id>] [reason:<text>]` | Run thread, or main channel with `run_id` | Restores a paused run to its prior state and restarts workflow recovery. |
| `/research-cancel [run_id:<id>] [reason:<text>]` | Run thread, or main channel with `run_id` | Cancels the run, aborts active OpenCode turns, requests cancellation of active jobs, and records the Discord actor and reason. |

Inside a run thread, pause, resume, and cancel resolve the run from the thread
and do not require an ID.

Discord does not currently expose list or status slash commands. Status is
shown by the run thread's editable status message.

## Approval Controls

Approve and Reject buttons appear in the run thread only when an action is
ready for human review. The approval brief describes the artifact or execution
scope and what pressing Approve authorizes.

Current gates include:

1. protocol and evaluation-contract proposal
2. generated evaluation-contract promotion, when a new harness is required
3. experiment execution, after Honeydew methodology review and deterministic
   preflight
4. final report acceptance

Reject opens a reason form. Rejection feedback is stored and returned to the
appropriate agent for revision. An approval is not evidence that execution
succeeded; job and artifact records remain authoritative.

## Starting An Arbitrary Task

Create a ZIP with:

```text
any-directory-name/
  problem.md
  eval_agent_prompt.md  # optional
```

`problem.md` should state:

- research question and hypotheses
- dataset source
- split and leakage constraints
- required baselines and controls
- metrics and uncertainty requirements
- expected artifacts
- compute or stopping constraints

Then use:

```text
/task-start archive:<attach ZIP>
```

Honeydew compiles the text into a validated `glasslab-task-spec-v1`.
Deterministic policy, not the model, selects:

- `workspace-cpu-ml-v1` or `workspace-gpu-ml-v1`
- the allowlisted runner image
- command and Kubernetes workload shape
- CPU, memory, GPU, wall-clock, and parallelism ceilings
- the initial immutable evaluation contract

The task filename has no semantic meaning.

## Dataset Boundary

For a local dataset, upload it first:

```text
/dataset-upload dataset:<attach file> name:income role:train contains_labels:true
```

The bot returns `glasslab-dataset://<sha256>`. Put that exact reference in
`problem.md`. Honeydew preserves it in the TaskSpec, after which the
orchestrator resolves it to a read-only shared-storage object and verifies its
digest during task preflight.

The generic path also supports datasets and other assets that:

- have a public, globally routable HTTPS URL
- require no login, cookie, token, or private-network access
- are no larger than 2 GiB per asset
- pass redirect, address, size, and optional expected-checksum validation

The task ZIP itself is limited to 16 MiB. Dataset files embedded in the ZIP are
not an execution-data path; reference an uploaded dataset or approved asset
URL. Discord uploads are limited to 100 MiB by service policy and may also be
limited by the Discord server. The authenticated HTTP endpoint streams files
up to the configured 2 GiB ceiling.

Not yet supported through Discord:

- directory or multi-file upload as one logical dataset
- private MinIO/S3 object selection
- Kaggle or other authenticated downloads
- datasets requiring license acceptance
- arbitrary container images or system packages

Package multi-file data into one archive before upload, or use a reviewed
external ingestion process and register the resulting immutable object.

## Evaluation Boundary

The generic `generic-task-integrity-v1` contract verifies declared metric keys,
artifacts, checksums, and provenance. It does not prove a domain-specific
scientific conclusion.

When structural validation is insufficient:

1. Honeydew specifies the required evaluator behavior.
2. Beaker drafts a bounded evaluator candidate.
3. The orchestrator seals and checksums it.
4. Honeydew reviews the read-only sealed copy.
5. A human approves promotion into the trusted contract catalog.

Neither OpenCode agent can edit a promoted contract or substitute an evaluator
entry point in a job request.

## HTTP Operator API

The HTTP API is for automation, recovery, and diagnostics. Operators should
not need to hand-write requests for normal Discord usage.

Read paths:

```text
GET /runs
GET /runs/{run_id}
GET /runs/{run_id}/events
GET /runs/{run_id}/events/stream
GET /runs/{run_id}/artifacts
GET /task-bundles
GET /task-bundles/{task_id}
GET /task-bundles/{task_id}/preflight
GET /datasets
GET /datasets/{dataset_id}
GET /actions/{action_id}
GET /health
GET /ready
```

State-changing paths require `X-Glasslab-Operator-Token` in the live
deployment:

```text
POST /runs
POST /task-bundles/import
POST /datasets/import
POST /runs/{run_id}/pause
POST /runs/{run_id}/resume
POST /runs/{run_id}/cancel
POST /actions/{action_id}/approve
POST /actions/{action_id}/reject
```

Do not put the operator token, Discord token, or webhook URL in documentation,
Git, shell history, or screenshots.

## Deployment Commands

GitHub Actions publishes a matched pair of immutable images under the full
commit SHA:

```text
ghcr.io/offensivegeneric/glasslab-workflow-api:<full-sha>
ghcr.io/offensivegeneric/glasslab-research-orchestrator:<full-sha>
```

Deploy that release from the canonical `.44` checkout:

```bash
cd /home/glasslab/cluster-config
./scripts/rollout-research-services.sh --sync
```

Roll back to a previously published release:

```bash
./scripts/rollout-research-services.sh --tag <full-commit-sha>
```

The rollout command does not build images locally. It applies service policy
and configuration, selects the exact images, waits for both Deployments, and
runs live readiness checks.

## Progress Snapshot

Implemented and live:

- separate Honeydew and Beaker OpenCode sessions and workspaces
- durable state, actions, jobs, artifacts, and append-only events
- protocol, evaluator-promotion, execution, and final-report approval gates
- Discord start, task-start, dataset upload, approval, rejection, pause,
  resume, and cancellation controls
- deterministic CPU/GPU task compilation, immutable uploaded datasets, and
  public asset ingestion
- bounded Kubernetes execution through `workflow-api`
- immutable evaluator enforcement and generated-contract promotion
- CI-published, commit-addressed control-service releases
- restart recovery and job reconciliation

Validated:

- 66 research-orchestrator tests
- 159 workflow-api tests
- mocked complete research workflow
- live OpenCode/Qwen structured task compilation
- live Discord threads, identities, approvals, rejection feedback, and
  cancellation projection
- live Discord registration of dataset upload, pause, and resume commands
- live immutable dataset upload, durable lookup, and checksum readback
- live pause/resume recovery of the Adult run into a new Beaker turn
- live Kubernetes rollout and service readiness
- Adult, Wine, and Fashion-MNIST task preflight

Benchmark milestone:

- Adult Income run `406b2d800d3b4e9a90af79e6b1b0ab55` was created from
  the pre-registered compatibility task.
- Honeydew drafted its protocol and the protocol was approved.
- The first Beaker implementation turn wrote experiment code but timed out
  before returning its structured matrix proposal.
- Pause/resume recovery started Beaker turn 3; no experiment Kubernetes Job
  had been submitted at the time of this update.
- This records a workflow milestone, not benchmark completion.
- Wine and Fashion-MNIST are preflight-ready but have not completed live runs.

The Adult, Wine, and Fashion-MNIST definitions are compatibility fixtures with
pre-registered datasets and task-specific evaluators. The generic extension
path is `/task-start`, not another hardcoded task entry.

## Current Limitations

- one active research run
- one orchestrator replica and SQLite WAL
- fixed approved repository and runtime profiles
- no authenticated remote dataset download or private object-store browser
- no Discord list or status commands
- no automatic Git push or pull request creation
- no arbitrary SSH, `kubectl`, secret access, or container publication for
  either agent
- no completed live end-to-end arbitrary-dataset task yet
- the two-node 70B runtime is slow enough that agent turns use a 30-minute
  deadline; cluster jobs do not hold an agent turn open

For architecture and trust-boundary details, read
[`research-orchestrator.md`](research-orchestrator.md).
