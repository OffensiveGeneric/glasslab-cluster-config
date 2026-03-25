# OpenClaw Shared-State Decision

This note narrows issue `#14`.

The repo already contains the artifacts needed to run the bounded experiment:

- a non-production shared-state PV/PVC example
- a migration test runbook
- rollback guidance

What remained unclear was the decision rule after the test.

## The Real Question

The real question is not:

- "can OpenClaw technically mount shared storage?"

It is:

- "does moving OpenClaw writable state to shared storage improve operator continuity enough to justify the added storage coupling?"

## Evidence That Would Support Migration

Shared storage becomes the better default only if the test shows all of these:

- OpenClaw starts cleanly on the shared claim
- writable state survives restart as expected
- WhatsApp/session continuity is materially improved
- file behavior is boring enough for day-to-day use
- rollback remains straightforward

## Evidence That Would Argue Against Migration

Keep the current local-PV default if any of these happen:

- startup behavior becomes flaky
- session or credential files behave oddly on shared storage
- latency or file semantics create visible operator friction
- rollback is messy or data handling becomes ambiguous

## Recommended Decision Rule

Use this rule after the test:

### Adopt shared state only if:

- the test is clean
- operator-visible continuity is materially better
- the storage behavior is boring enough to support daily use

### Keep local PV if:

- the test is only "technically works"
- the operator benefit is minor
- the shared-storage behavior is strange or fragile

That is important because OpenClaw is a good relocation candidate, but it is still not worth making the default path uglier just to claim a node-loss-tolerance win.

## What This Issue Should Be Considered Done By

Issue `#14` is materially advanced when:

1. the test artifacts exist in the repo
2. the migration test is run once
3. the result is written down clearly
4. the repo recommendation is updated to either:
   - keep local PV as default
   - or adopt shared storage for OpenClaw state

## Bottom Line

The next meaningful step is no longer more design.

It is running the test once and making a decision from observed behavior.

## References

- `runbooks/test-openclaw-shared-state.md`
- `node-loss-tolerance-phased-plan.md`
- `stateful-service-recovery-matrix.md`
