# Execution Implementation Checklist

This note turns issue `#44` into a concrete implementation checklist.

The architecture decision is already made:

- execution remains deterministic and backend-owned
- `workflow-api` plus `JobSubmitter` is the first implementation boundary

What remains is preserving and tightening that boundary.

## Minimum Implementation Goal

Make accepted runs move through a bounded, auditable execution path from:

- canonical `RunManifest`

to:

- Kubernetes Job submission
- live status resolution
- log and artifact exposure

without introducing an LLM-owned execution layer.

## Checklist

### 1. Keep Execution Input Narrow

Execution should accept only:

- an already validated run manifest or accepted run record

It should not accept:

- vague prompt context
- free-form execution repair instructions
- unvalidated design drafts

### 2. Keep Submission Deterministic

The `JobSubmitter` path should continue to own:

- job-name derivation
- runner spec derivation
- Kubernetes Job creation

No model should author or mutate Job specs in the first pass.

### 3. Fail Before Submission When Invalid

If required inputs or workflow-specific submission fields are missing:

- fail before the Kubernetes API is called
- keep the failure explicit in backend logs or returned detail

### 4. Keep Live Status And Logs Backend-Owned

Lifecycle tracking should continue to come from:

- Kubernetes job status
- pod logs
- persisted run-record state

OpenClaw and future agents may summarize this, but should not become the source
of truth.

### 5. Keep Artifact Exposure Explicit

Execution should continue to expose:

- run status
- logs
- artifact indexes

through backend APIs rather than ad hoc filesystem assumptions.

### 6. Keep Rerun Scope Bounded

Approved reruns should continue to reuse:

- explicit stored scope
- bounded backend validation

They should not become an informal execution shortcut.

## Suggested Rollout / Verification

1. keep `JobSubmitter` as the only execution handoff
2. confirm tests cover invalid pre-submission cases
3. keep status/log/artifact retrieval explicit in backend APIs
4. keep OpenClaw outside the execution engine

## Success Criteria

The issue is materially advanced when:

- execution inputs are explicit and narrow
- pre-submit failures are explicit
- lifecycle state remains auditable
- no model-owned execution path has been introduced

## Bottom Line

For execution, the next win is preserving a boring deterministic control plane,
not adding agency.

## References

- `execution-boundary.md`
- `services/workflow-api/app/job_submission.py`
- `services/workflow-api/app/main.py`
