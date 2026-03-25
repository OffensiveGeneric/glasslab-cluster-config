# Reporting Close Criteria

This note narrows issue `#45`.

The main design question is already answered:

- reporting stays grounded in explicit artifacts
- the existing deterministic `reporter` service is the first implementation boundary

What remained unclear was when the issue should be considered materially resolved.

## Close Criteria

Issue `#45` should be considered closeable when these are true:

1. the deterministic reporting boundary is documented
2. the implementation checklist exists
3. reporter ownership versus `workflow-api` ownership is explicit
4. the remaining work is wiring or presentation detail, not unresolved architecture

## Current Status Against Those Criteria

### 1. Boundary documented

Satisfied.

Reference:

- `reporting-boundary.md`

### 2. Implementation checklist exists

Satisfied.

Reference:

- `reporting-implementation-checklist.md`

### 3. Ownership split explicit

Satisfied.

Current split:

- `workflow-api` decides when reporting runs and what artifacts are in scope
- `reporter` renders the grounded report

### 4. Remaining work is wiring-only

Satisfied.

The remaining work is now things like:

- backend trigger integration
- artifact/result exposure
- optional later prose restatement

Not:

- whether a free-form reporting agent should exist

## What Should Not Keep This Issue Open

Do not keep this issue open merely because:

- richer notebook-style output may appear later
- operator-facing presentation could become nicer
- optional model-backed prose rewriting might exist later

Those are separate follow-on concerns.

## Bottom Line

This issue is no longer an unresolved design problem.

The deterministic reporting answer is already in place.

## References

- `reporting-boundary.md`
- `reporting-implementation-checklist.md`
- `evaluation-implementation-checklist.md`
