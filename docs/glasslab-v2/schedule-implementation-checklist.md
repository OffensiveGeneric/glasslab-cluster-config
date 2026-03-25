# Schedule Implementation Checklist

This note turns issue `#30` into concrete backend work.

The design questions are mostly settled already:

- stored schedule records belong in `workflow-api`
- execution must happen through a bounded backend worker
- every execution attempt must re-validate scope and fail closed on drift

What remains is implementation.

## Digest path checklist

- keep stored digest schedule records bounded to explicit filters and time windows
- add one backend worker loop that claims due digest schedules without relying on OpenClaw
- fetch only existing run records, artifacts, and evaluation outputs
- render one bounded digest result record or artifact reference
- store one execution record per attempt with status and failure reason

## Approved rerun path checklist

- require the stored schedule to reference an already accepted source run or reviewed design context
- re-check workflow ID, dataset URI, model IDs, runner image, and resource profile before execution
- refuse execution when any approved field has widened or drifted
- create a new run only through the normal `workflow-api` validation path
- submit Kubernetes work only after manifest validation succeeds

## Worker checklist

- run the worker as an internal backend service or CronJob in `glasslab-v2`
- claim due schedules with one clear ownership path to avoid duplicate execution
- write explicit execution records with `started_at`, `finished_at`, `result_status`, and failure reason
- surface digest artifact references or resulting run IDs back through `workflow-api`
- disable or quarantine schedules that repeatedly fail closed on the same validation problem

## API checklist

- keep OpenClaw limited to schedule creation, listing, disabling, and later status reads
- keep `run-now` behind the exact same validation path as due-time execution
- add schedule execution record endpoints only after the worker is producing real records
- do not add free-form unattended execution inputs to OpenClaw

## Rollout checklist

1. implement digest worker first
2. add execution records and read APIs second
3. implement approved rerun worker third
4. add narrow `run-now` only after both worker paths are stable

## Close rule

Issue `#30` should be considered materially advanced when:

- due digest schedules execute through a backend worker
- execution attempts create explicit audit records
- approved reruns fail closed on scope drift
- OpenClaw still has no direct execution-bypass path
