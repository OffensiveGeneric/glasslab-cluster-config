# Run-Preparation Implementation Checklist

This note turns issue `#41` into a concrete implementation checklist.

The architecture decision is already made:

- canonical run preparation stays inside `workflow-api`
- no free-form run-preparation agent should own final execution control fields

What remains is tightening and preserving the deterministic path.

## Minimum Implementation Goal

Make the backend-derived run path explicit and reliable from:

- approved design draft

to:

- validated `RunCreateRequest`
- canonical `RunManifest`
- bounded job-submission handoff

## Checklist

### 1. Keep Design Draft As The Last Model-Assisted Boundary

The handoff into run preparation should be:

- reviewed design draft only

Run preparation should not accept:

- vague prompt context
- unreviewed missing inputs
- free-form model suggestions as execution truth

### 2. Fail Closed On Draft Readiness

If the design draft is not `ready_for_run`:

- do not derive a run
- do not try to repair unresolved fields automatically
- surface the blocking reason plainly

### 3. Keep Registry Validation Central

`workflow-api` should continue to own:

- allowed workflow lookup
- allowed model validation
- resource-profile validation
- required input validation

### 4. Keep Manifest Derivation Deterministic

The final `RunManifest` should be built from:

- reviewed design draft fields
- workflow registry policy
- explicit source-record linkage

It should not depend on live model inference.

### 5. Preserve Source Lineage

The resulting run should continue to carry explicit lineage such as:

- `source_design_id`
- `source_intake_id`
- workflow ID

That matters for later evaluation and reporting.

### 6. Keep Submission Handoff Separate

Manifest derivation and job submission should remain distinct backend steps:

- derive and validate first
- submit second

That keeps it possible to inspect failures before Kubernetes is involved.

## Suggested Rollout / Verification

1. keep `POST /runs/from-latest-design-draft` as the canonical path
2. confirm validation tests cover rejected drafts and invalid models/resources
3. keep job-submission logic downstream of deterministic manifest creation
4. log or expose enough metadata to explain why a draft did or did not become a run

## Success Criteria

The issue is materially advanced when:

- the deterministic derivation path is explicit
- blocking conditions are explicit
- source lineage is preserved
- no model-owned execution-control path has crept into run creation

## Bottom Line

For run preparation, the next win is preserving a boring deterministic boundary,
not adding agency.

## References

- `run-preparation-boundary.md`
- `services/workflow-api/app/validation.py`
- `services/workflow-api/app/job_submission.py`
