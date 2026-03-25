# Node-Loss Tolerance Phased Plan

This note turns issue `#13` into a phased execution sequence.

The repo already contains the service classification and the first candidate choices.

What was still missing was a simple answer to:

- what should actually happen first
- what should wait
- what should not be bundled together

## Phase 1: Recovery Discipline Everywhere

Do first:

- keep or add backup/restore procedures for every local-PV-backed service
- keep the procedures explicit and operator-usable
- verify at least the smaller restores in practice

Services in scope:

- Postgres
- MinIO
- OpenClaw writable state
- NATS JetStream

Why this phase comes first:

- it improves survivability immediately
- it does not require a risky storage migration
- it creates a baseline even if later relocation work stalls

## Phase 2: OpenClaw Shared-State Experiment

Do second:

- test relocating only OpenClaw writable state to shared storage
- validate startup, restart continuity, and rollback

Why this is next:

- OpenClaw state is small
- the operator-visible benefit is high
- rollback is relatively straightforward

Do not widen this phase to include:

- Postgres
- MinIO
- NATS topology changes

## Phase 3: NATS Durability Decision

Do third:

- decide whether JetStream needs anything stronger than the current local-PV + restore posture

Possible outcomes:

- keep current posture
- move to shared-backed storage
- move to a more explicit replicated NATS design

Why later:

- the durability need is still less urgent than database correctness
- the best answer depends on real usage, not theoretical neatness

## Phase 4: Postgres And MinIO Deliberate Storage/HA Design

Do last:

- choose deliberate recovery objectives
- choose backup and restore guarantees
- only then choose whether HA or storage migration is worth the cost

Why last:

- these are the most correctness-sensitive stateful services
- casual migration would be worse than current known limitations

## What Not To Do

Avoid these mistakes:

- bundling all stateful-service changes into one migration wave
- treating NFS as an automatic fix for every local-PV service
- moving Postgres or MinIO just because OpenClaw moves cleanly
- conflating restart durability with node-loss tolerance

## Practical Priority Order

1. backup/restore drills and docs stay current
2. OpenClaw shared-state relocation test
3. NATS durability decision
4. Postgres and MinIO long-term design

## Bottom Line

The next meaningful improvement is not "make the platform HA."

It is:

- make recovery real everywhere
- then pick one small high-value relocation candidate
- then only escalate to database-grade storage design where it is justified

## References

- `stateful-service-recovery-matrix.md`
- `node-loss-tolerance-next-steps.md`
- `runbooks/test-openclaw-shared-state.md`
