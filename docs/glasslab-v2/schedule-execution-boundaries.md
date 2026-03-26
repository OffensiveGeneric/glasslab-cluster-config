# Schedule Execution Boundaries

This note narrows issue `#30`.

Issue `#55` sharpens the current execution contract so the repo does not describe schedule handling as more durable than it is.

The current repo already has:

- approval-tier guidance
- stored schedule endpoints in `workflow-api`

What still needs to stay explicit is the execution boundary.

## Core rule

A stored schedule record is not permission to execute arbitrary work.

It is permission to attempt one specific bounded operation and fail closed if the reviewed scope no longer matches reality.

## Digest schedules

Digest schedules are `tier-1-read-only`.

They may:

- gather existing records
- gather existing artifacts
- produce summaries
- notify or surface a digest result

They may not:

- create new workflow runs
- mutate cluster infrastructure
- widen scope beyond the declared digest filter

## Approved rerun schedules

Approved rerun schedules are only valid when the source run still anchors the allowed scope.

Before execution, the backend should verify:

- the source run still exists
- the source run succeeded
- the source run approval tier is still `tier-2-approved-execution`
- the workflow ID is unchanged
- the dataset URI is unchanged or still allowlisted
- the model IDs are unchanged or still allowlisted
- the runner image is unchanged or still allowlisted
- the resource profile is unchanged or still allowed

If any of those checks fail, the schedule should:

- not submit a Kubernetes Job
- record a fail-closed reason
- remain disabled or require explicit review

## Current Execution Contract

The current `workflow-api` implementation already enforces a narrow audit shape that should stay visible in docs and tests:

- each due execution attempt writes a separate `ScheduledExecutionRecord`
- the schedule row is updated with `last_execution_at`, `last_result_status`, and `last_result_detail`
- a second execution in the same UTC minute is skipped by the current helper logic
- the execution history is the append-only audit trail, not the mutable schedule row
- `GET /scheduled-executions` and `list_executions(schedule_id=...)` are the stable read paths for that audit trail

That is the minimum contract to preserve while scheduling stays inside `workflow-api`. It is not a claim that the scheduler itself is durable yet.

## `run-now` boundary

A future `run-now` endpoint should not bypass the schedule checks.

It should:

- reuse the same backend validation path as due-time execution
- create an explicit execution record
- fail closed on the same scope drift rules

That keeps `run-now` as an operator convenience, not a policy bypass.

## OpenClaw role

OpenClaw should stay outside the scheduler core.

Good roles:

- create a bounded schedule record
- list active schedules
- disable a schedule
- request a `run-now` on an already valid stored schedule

Bad roles:

- invent new unattended execution scope in free text
- bypass backend validation
- decide on its own to widen a schedule after drift

## Practical conclusion

Issue `#30` should keep moving in this order:

1. explicit stored schedule records
2. backend execution worker with fail-closed validation
3. execution records and audit trail
4. only then narrow OpenClaw schedule-management actions

That keeps unattended work aligned with the backend-first architecture instead of turning the operator shell into a hidden autonomy layer.
