# Schedule Implementation Checklist

This note turns issue `#30` into concrete backend work.

The design questions are mostly settled already:

- stored schedule records belong in `workflow-api`
- execution must happen through a bounded backend worker
- every execution attempt must re-validate scope and fail closed on drift

The first bounded digest-execution path now exists in repo code.

## Current repo state

- `workflow-api` now owns:
  - due-digest execution helper logic
  - `POST /digest-schedules/run-due`
  - `GET /scheduled-executions`
  - explicit `ScheduledExecutionRecord` objects in the in-memory store
- `services/schedule-worker` now exists as a bounded worker wrapper that calls the due-digest path through `workflow-api`

This is intentionally only the first unattended lane:

- digest schedules
- read-only summaries
- no arbitrary job creation

## Remaining digest path checklist

- fetch only existing run records, artifacts, and evaluation outputs
- render one bounded digest result artifact or persistent digest record instead of only an in-memory payload
- add worker ownership / claim rules if multiple replicas are ever allowed
- persist execution records durably once the backend store is no longer in-memory

## Approved rerun path checklist

- require the stored schedule to reference an already accepted source run or reviewed design context
- re-check workflow ID, dataset URI, model IDs, runner image, and resource profile before execution
- refuse execution when any approved field has widened or drifted
- create a new run only through the normal `workflow-api` validation path
- submit Kubernetes work only after manifest validation succeeds

## Remaining worker checklist

- deploy the worker as an internal backend service or CronJob in `glasslab-v2`
- claim due schedules with one clear ownership path to avoid duplicate execution
- surface digest artifact references or resulting run IDs back through `workflow-api`
- disable or quarantine schedules that repeatedly fail closed on the same validation problem

## API checklist

- keep OpenClaw limited to schedule creation, listing, disabling, and later status reads
- keep `run-now` behind the exact same validation path as due-time execution
- add schedule execution record endpoints only after the worker is producing real records
- do not add free-form unattended execution inputs to OpenClaw

## Rollout checklist

1. deploy the digest worker first
2. persist digest execution outputs beyond memory
3. implement approved rerun worker third
4. add narrow `run-now` only after both worker paths are stable

## Close rule

Issue `#30` should be considered materially advanced when:

- due digest schedules execute through a backend worker
- execution attempts create explicit audit records
- approved reruns fail closed on scope drift
- OpenClaw still has no direct execution-bypass path
