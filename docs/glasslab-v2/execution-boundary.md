# Execution Boundary

This note resolves the intended shape of the execution stage.

The key decision is:

- execution remains deterministic and backend-owned
- there is no need for a separate autonomous execution agent in the first
  implementation

## What Execution Owns

Execution is the bounded handoff from an already-approved run record to the
actual Kubernetes Job lifecycle.

That includes:

- submitting the run manifest to the configured job-submission backend
- creating the initial accepted run record
- resolving live status as the Job progresses
- surfacing logs and artifacts
- supporting bounded approved-rerun schedule records

In the current repo, that ownership already lives in `workflow-api` plus the
`JobSubmitter` boundary.

## What Execution Should Not Own

Execution should not:

- reinterpret the research goal
- mutate the approved workflow family
- invent missing inputs
- widen model or resource scope
- bypass registry validation
- decide on its own to rerun failed or drifted work

If a run is invalid, execution should fail before submission rather than trying
to repair it opportunistically.

## Current Implementation Reality

The current code path already matches the intended boundary:

- `create_run_record(...)` validates the final request against the approved
  workflow definition
- `JobSubmitter.submit_run(...)` is the bounded submission interface
- `resolve_run_status(...)` merges persisted artifact status and live job status
- approved rerun scheduling records are derived from succeeded runs with explicit
  allowlisted scope

That is the right first implementation shape.

## OpenClaw Relationship

OpenClaw should never become the execution engine.

Good roles:

- request a bounded run creation path that `workflow-api` validates
- ask for run status
- ask for logs or artifacts
- request schedule creation for already-approved reruns

Bad roles:

- author Kubernetes Job specs directly
- decide to resubmit failed work without backend checks
- widen execution scope through chat-only reasoning

## Future Helper Services

If a later helper service exists in the execution lane, it should remain
deterministic and internal.

Allowed future role:

- queue handling
- lifecycle bookkeeping
- artifact indexing

Disallowed future role:

- free-form model-driven execution planning
- silent mutation of approved manifests

## Issue Resolution Effect

This means issue `#44` should be treated as:

- formalizing and preserving the deterministic execution boundary
- tightening the `workflow-api` to job-submission contract where needed
- keeping execution state transitions explicit and auditable
