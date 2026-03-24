# Approval-Tier-Gated Unattended Operations Plan

This note turns the current unattended-operations idea into a concrete backend plan.

The goal is not "let the agent do anything on a timer."

The goal is:

- allow recurring low-risk digest/reporting work
- allow recurring reruns of already approved workflows
- keep all unattended behavior inside explicit approval tiers
- fail closed when a request escapes the reviewed boundary

## Scope

This plan covers two unattended operation families:

- recurring digests
- recurring approved reruns

It does not cover:

- new workflow-family creation
- arbitrary infrastructure mutation
- arbitrary shell execution
- broad autonomous tool use from OpenClaw

## Why This Exists

Glasslab eventually wants backend stage agents and unattended background work.

But the current stack should only automate the kinds of tasks that fit the existing trust model:

- Tier 1:
  - read-only summaries, digests, notifications
- Tier 2:
  - bounded reruns of approved workflows with approved models, datasets, and runner images
- Tier 3:
  - explicit human approval required

That means unattended operations should be expressed as stored backend schedules and execution policies, not hidden prompt logic.

## Core Principle

An unattended operation should be a first-class stored record with:

- operation type
- approval tier
- owner
- schedule
- allowed workflow or digest scope
- last run status
- explicit disable switch

OpenClaw may trigger or summarize these records, but `workflow-api` should own them.

## Proposed Record Types

### 1. Digest Schedule

Purpose:

- create recurring summaries from existing records and artifacts

Examples:

- daily completed-run digest
- nightly literature-intake queue digest
- failure digest for runs that ended in `failed`

Minimum fields:

- `schedule_id`
- `created_at`
- `status`
- `operation_type=digest`
- `approval_tier=tier-1-read-only`
- `owner`
- `cron_expr`
- `digest_kind`
- `scope_filter`
- `last_execution_at`
- `last_result_status`

### 2. Approved Rerun Schedule

Purpose:

- rerun an already approved workflow on a defined cadence without widening scope

Examples:

- daily rerun of a reviewed benchmark
- weekly literature-to-experiment draft refresh against a fixed dataset path

Minimum fields:

- `schedule_id`
- `created_at`
- `status`
- `operation_type=approved-rerun`
- `approval_tier`
- `owner`
- `cron_expr`
- `source_design_id`
- `source_run_id`
- `workflow_id`
- `allowed_dataset_uri`
- `allowed_model_ids`
- `allowed_runner_image`
- `resource_profile`
- `last_execution_at`
- `last_result_status`

## Enforcement Rules

### Tier 1: Digests And Notifications

Allowed:

- read-only summaries
- literature queue summaries
- run-status summaries
- artifact summary generation

Requirements:

- no Kubernetes write actions
- no workflow creation
- no approval-scope expansion

### Tier 2: Approved Reruns

Allowed:

- only runs derived from an already reviewed design or accepted run
- only approved workflow IDs
- only approved runner images
- only approved model IDs and resource profiles
- dataset location must remain fixed or come from an approved allowlist

Requirements:

- manifest derivation stays deterministic
- rerun must not widen execution scope relative to the reviewed source
- if any required field drifts, disable and require review

### Tier 3: Human Approval Required

Always required for:

- new workflow families
- new datasets outside the approved allowlist
- new models outside the approved allowlist
- infrastructure changes
- any request to widen a schedule's execution scope

## Suggested API Surface

First pass:

- `POST /digest-schedules`
- `GET /digest-schedules`
- `POST /digest-schedules/{schedule_id}/disable`
- `POST /approved-rerun-schedules/from-latest-run`
- `GET /approved-rerun-schedules`
- `POST /approved-rerun-schedules/{schedule_id}/disable`

Second pass:

- `POST /digest-schedules/{schedule_id}/run-now`
- `POST /approved-rerun-schedules/{schedule_id}/run-now`
- `GET /scheduled-executions/{execution_id}`

## Execution Path

### Digest Schedule

1. stored schedule becomes due
2. backend scheduler or worker claims it
3. worker gathers records/artifacts
4. deterministic summary input is produced
5. optional narrative summarizer produces digest text
6. result is stored and optionally surfaced through OpenClaw

### Approved Rerun

1. stored rerun schedule becomes due
2. backend worker fetches the reviewed source design/run
3. backend verifies workflow ID, model IDs, dataset URI, runner image, and resource profile are still allowed
4. backend creates a new accepted run record if the scope is unchanged
5. Kubernetes Job is submitted
6. execution and artifacts follow the normal bounded run path

## OpenClaw Role

OpenClaw should stay narrow here too.

Good no-arg operator actions:

- create last-run digest schedule
- list active schedules
- disable latest schedule
- create approved rerun schedule from latest accepted run

Bad operator actions:

- free-form "schedule whatever you think is useful"
- unconstrained cron creation with arbitrary workflow inputs

## Storage And Audit

These schedule records should eventually live in durable backend storage, not only in memory.

Each schedule execution should produce:

- execution timestamp
- resulting run ID or digest artifact ID
- success/failure status
- reason for any fail-closed rejection

## Immediate Implementation Order

1. document the approval-tier contract and allowed operation shapes
2. add schedule record types in `workflow-api`
3. implement Tier 1 digest schedules first
4. implement Tier 2 approved reruns second
5. add narrow no-arg OpenClaw actions only after backend records exist

## Recommendation

Build unattended operations as explicit backend schedules.

Do not model them as long-lived autonomous chat sessions.

That keeps the unattended path aligned with the current Glasslab strengths:

- deterministic backend state
- bounded workflow execution
- narrow operator entrypoints
- clear approval boundaries
