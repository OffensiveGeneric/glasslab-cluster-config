# Schedule Worker Plan

This note turns issue `#30` from "stored schedule records exist" into "how should due schedules actually execute?"

The current repo already has:

- stored schedule record endpoints
- approval-tier rules
- execution-boundary notes

What remains is the worker shape that will claim due schedules and execute them without widening the trust boundary.

## Worker Responsibility

The schedule worker should do exactly three things:

1. find due schedule records
2. re-validate that execution is still allowed
3. either execute the bounded action or fail closed with an audit record

It should not:

- infer new workflows
- widen allowed datasets or models
- accept free-form tool instructions from OpenClaw

## Supported Operation Types

### 1. Digest schedules

Allowed worker action:

- gather existing records and artifacts
- produce a bounded digest output
- store execution result metadata

Execution rule:

- stay `tier-1-read-only`
- no Kubernetes write path required

### 2. Approved rerun schedules

Allowed worker action:

- fetch the referenced latest accepted run or design context
- verify the stored scope is still valid
- create a new accepted run record only if the reviewed scope has not widened
- submit the normal bounded Kubernetes Job

Execution rule:

- fail closed if any approved field has drifted

## Required Re-Validation

Before every execution, the worker should re-check:

- schedule is still `active`
- approval tier is still eligible
- workflow ID is still approved
- dataset URI is still allowed
- model IDs are still allowed
- runner image is still allowed
- resource profile is still allowed

If any check fails:

- mark the execution as rejected or failed-closed
- keep an audit reason
- do not submit work

## Suggested Execution Records

The worker should eventually produce one execution record per attempt with at least:

- `execution_id`
- `schedule_id`
- `started_at`
- `finished_at`
- `result_status`
- `failure_reason`
- `result_run_id` or digest artifact reference

That gives the system an audit trail without making OpenClaw the scheduler of record.

## Suggested Rollout Order

1. digest worker first
2. approved-rerun worker second
3. optional `run-now` endpoint only after both worker paths are stable

Why:

- digest execution is lower risk
- approved reruns touch actual Kubernetes execution
- `run-now` should reuse the same worker validation path, not bypass it

## OpenClaw Role

OpenClaw should remain limited to:

- creating schedule records
- listing schedule records
- disabling schedule records
- summarizing execution status later

It should not:

- directly execute schedule jobs
- bypass the worker validation loop

## Bottom Line

The next meaningful implementation step for unattended operations is not more schedule endpoints.

It is one bounded schedule worker that re-validates every due schedule before acting.

## References

- `approval-tier-unattended-ops-plan.md`
- `workflow-api-schedules.md`
- `schedule-execution-boundaries.md`
