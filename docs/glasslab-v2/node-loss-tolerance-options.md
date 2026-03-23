# Node-Loss Tolerance Options

This note exists to answer a specific next-step question:

How should Glasslab move from "survives pod restart" toward "survives node loss"?

## Current Reality

Today the platform is in a better place than it was during the early `emptyDir` phase, but it is not node-loss tolerant yet.

What is true now:

- Postgres survives pod replacement because it is on a retained local PV on `node01`
- MinIO survives pod replacement because it is on a retained local PV on `node01`
- OpenClaw state survives pod replacement because it is on a retained local PV on `node01`
- NATS JetStream survives pod replacement because it is on a retained local PV on `node05`
- shared datasets and shared artifacts are available through NFS across the cluster

What is not true yet:

- loss of `node01` would still take out Postgres, MinIO, and OpenClaw writable state
- loss of `node05` would still take out NATS JetStream state
- the system does not yet have a storage model that lets those stateful services relocate safely after node loss

## The Main Design Split

There are three broad ways to improve node-loss tolerance.

### 1. Put more writable state on shared storage

This is the simplest conceptual move.

Advantages:

- easier pod relocation
- less dependence on one worker node
- uses infrastructure that already exists in the lab

Risks:

- casual NFS is not automatically a good database substrate
- service semantics still matter
- shared storage solves mobility more than it solves consistency or performance

Best fit:

- small writable state
- shared artifacts
- datasets
- some gateway/session state

Weak first fit:

- primary Postgres data without deliberate validation
- primary MinIO data without a clearly chosen operating model

### 2. Keep local storage but add service-level replication

This is the stronger long-term answer for important state.

Advantages:

- better alignment with stateful system semantics
- less reliance on one shared filesystem behaving like a database disk
- more realistic path for durable research infrastructure

Risks:

- more operational complexity
- more moving parts
- likely more work than the lab needs for every service

Best fit:

- Postgres, if it becomes more central and harder to reconstruct
- MinIO, if it becomes the real artifact source of truth at larger scale
- NATS, if JetStream becomes a core durable event substrate instead of a simple internal bus

### 3. Treat node loss as a backup-and-restore event

This is the minimum-complexity path.

Advantages:

- simplest to operate
- compatible with the current local-PV model
- good enough for some non-critical services

Risks:

- slower recovery
- not true failover
- still means downtime and operator work

Best fit:

- services whose state is small and reconstructable
- intermediate stages before a stronger HA design exists

## Service-By-Service Recommendation

### NATS

This is the easiest next place to improve after the current local-PV step.

Why:

- its state is smaller than Postgres or MinIO
- it is already logically separated as an internal bus
- the system can tolerate a narrower experiment surface here

Realistic next choices:

- keep the current local PV and rely on backup/restore for now
- evaluate whether JetStream state can move to shared storage acceptably
- later consider a multi-node NATS topology only if event durability becomes central

### OpenClaw state

This is a reasonable candidate for shared storage earlier than the databases.

Why:

- current state is relatively small
- loss is painful operationally, especially for WhatsApp/device/session continuity
- it is a better shared-storage candidate than Postgres

Realistic next choices:

- keep current local PV with backup/restore
- move writable gateway state onto shared storage if the lab wants better relocation

### Postgres

This should not be moved casually just because NFS exists.

Why:

- database semantics matter more than convenience
- node-loss tolerance here should come from a deliberate storage or HA decision

Realistic next choices:

- keep local PV plus backup/restore until stronger HA need exists
- evaluate a more serious shared-storage path only after measurement
- later move toward real Postgres HA if workflow state becomes mission-critical

### MinIO

This is between OpenClaw and Postgres in difficulty.

Why:

- it is already the right artifact sink
- but it is still stateful infrastructure, not just a file cache

Realistic next choices:

- keep local PV plus backup/restore now
- consider whether artifacts should be mirrored to NFS for recovery convenience
- only later decide whether MinIO itself should be distributed or shared-storage-backed

## What NFS Already Solves

NFS already helps with:

- shared datasets
- shared artifacts
- reducing some node-local friction
- cross-node data visibility

NFS does not yet solve:

- node-loss tolerance for the local-PV-backed core services
- image-distribution pinning
- GPU placement constraints
- higher-level state replication

## Practical Near-Term Path

The pragmatic order is:

1. keep the current local-PV wins
2. keep using NFS for shared datasets and artifacts
3. add backup and restore discipline for all local-PV-backed stateful services
4. evaluate OpenClaw state as the first realistic shared-storage relocation candidate
5. evaluate NATS as the next likely service to improve beyond single-node durability
6. leave Postgres and MinIO for a more deliberate HA/storage decision

## Decision Test

When deciding whether to move a service toward node-loss tolerance, ask:

1. Is this service painful to reconstruct after node loss?
2. Is its writable state small enough for shared storage to be boring?
3. Would backup/restore be good enough for now?
4. Would node loss create unacceptable downtime for this service?
5. Does the service need relocation, or just better recovery?

Short version:

- use NFS for shared data first
- use local PVs for simple single-node durability
- use replication or more deliberate storage design only where node-loss tolerance is truly worth the operational cost
