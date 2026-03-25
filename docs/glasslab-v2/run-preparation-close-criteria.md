# Run-Preparation Close Criteria

This note narrows issue `#41`.

The main design question is already answered:

- canonical run preparation stays inside `workflow-api`
- no free-form run-preparation agent should own execution-control fields

What remained unclear was when the issue should be considered materially resolved.

## Close Criteria

Issue `#41` should be considered closeable when these are true:

1. the deterministic run-preparation boundary is documented
2. the implementation checklist exists
3. the canonical backend path is explicit
4. the remaining work is ordinary backend hardening, not an open architecture question

## Current Status Against Those Criteria

### 1. Boundary documented

Satisfied.

Reference:

- `run-preparation-boundary.md`

### 2. Implementation checklist exists

Satisfied.

Reference:

- `run-preparation-implementation-checklist.md`

### 3. Canonical backend path is explicit

Satisfied.

Current path:

- `POST /runs/from-latest-design-draft`
- deterministic validation in `workflow-api`
- deterministic submission handoff through `JobSubmitter`

### 4. Remaining work is implementation-only

Satisfied.

The remaining work is now things like:

- test coverage
- logging and observability
- stricter validation edges

Not:

- whether run preparation should become a model-owned stage

## What Should Not Keep This Issue Open

Do not keep this issue open merely because:

- later advisory model prompts might exist
- bounded design-agent work exists upstream
- execution and reporting still have their own implementation work

Those are separate concerns.

## Bottom Line

This issue is no longer an unresolved design problem.

The deterministic run-preparation answer is already in place.

## References

- `run-preparation-boundary.md`
- `run-preparation-implementation-checklist.md`
- `execution-implementation-checklist.md`
