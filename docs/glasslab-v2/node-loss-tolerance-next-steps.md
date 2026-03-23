# Node-Loss Tolerance Next Steps

This note turns the broader node-loss discussion into a concrete near-term plan.

## Recommended Immediate Paths

The two most reasonable next moves are:

1. add backup and restore discipline for every local-PV-backed stateful service
2. evaluate OpenClaw state as the first shared-storage relocation candidate

These are the best next steps because they improve recovery and reduce operational pain without forcing a casual NFS migration for Postgres or MinIO.

## Path 1: Backup And Restore Discipline

Scope:

- Postgres local PV on `node01`
- MinIO local PV on `node01`
- OpenClaw writable state on `node01`
- NATS JetStream local PV on `node05`

Goal:

- make node loss survivable as an operator procedure even before true failover exists

Deliverables:

- documented backup locations and cadence
- documented restore procedure for each service
- at least one tested restore drill for the smallest services first
- explicit statement of what is and is not recovered by each procedure

Why first:

- lowest architectural risk
- improves recovery immediately
- compatible with the current local-PV layout

## Path 2: OpenClaw State Relocation Candidate

Scope:

- OpenClaw writable state only
- WhatsApp/device/session continuity only

Goal:

- determine whether small gateway state can move from local PV to shared storage without creating operational weirdness

Deliverables:

- a non-production test manifest or branch
- a migration test from local PV to shared storage
- restart verification
- explicit rollback path back to local PV

Why second:

- smaller and safer than moving Postgres or MinIO
- high operator value because chat-channel continuity matters
- directly advances node-loss tolerance for the operator gateway

## Deferred For Now

### Postgres

Do not move casually to NFS.

Next work should be design work, not an immediate cutover:

- recovery objectives
- backup/restore path
- eventual HA decision if workflow state becomes central

### MinIO

Do not move casually to NFS as the first node-loss step.

Next work should be:

- backup and recovery discipline
- decide whether artifact mirroring to shared storage is useful before any primary-storage migration

### NATS Beyond Local PV

The current local-PV step is good enough for now.

Next work should be:

- document JetStream backup/restore expectations
- only later decide between shared-storage-backed JetStream and a more explicit multi-node NATS topology

## Recommendation Summary

Near-term order:

1. backup/restore procedures for all local-PV-backed services
2. OpenClaw shared-state experiment
3. NATS recovery design
4. Postgres and MinIO deliberate HA/storage design later

This keeps the platform moving toward node-loss tolerance without pretending the NFS server alone solves every stateful-service problem.
