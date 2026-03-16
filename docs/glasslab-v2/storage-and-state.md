# Storage And State

Glasslab v2 is live, but its durable-storage story is still in the bring-up phase.

## Current posture

- the cluster has no `StorageClass`
- `glasslab-v2` currently has no PVCs
- Postgres uses `emptyDir`
- MinIO uses `emptyDir`
- NATS uses `emptyDir`
- OpenClaw writable state uses `emptyDir`

This means the current live path is operational, not durable.

## Intended storage strategy

The intended first durable v2 step is:

- keep the cluster-wide default `StorageClass` unset
- use explicit static local PV/PVC wiring for the first durable v2 services
- store artifacts in MinIO instead of on per-run PVCs
- revisit a shared CSI-backed default `StorageClass` only after the lab deliberately chooses and operates one

This matches the existing v1 pattern in `kubeadm/agent-stack/02-persistent-volume-claims.yaml`, where single-node local PVs are explicit and reviewable.

Future storage placeholders live under `kubeadm/glasslab-v2/storage/`.

## Workload expectations

### Durable volumes required

- Postgres: durable PV required before treating run state as persistent
- MinIO: durable PV required before treating artifacts or reports as persistent
- optional MLflow: durable PV required if enabled

### Ephemeral is acceptable for now

- `workflow-api`: stateless deployment
- OpenClaw runtime bundle: generated from ConfigMap
- OpenClaw tmp/state: acceptable as ephemeral for first validation
- NATS: acceptable as ephemeral while v2 does not rely on JetStream as a durable source of truth

### Artifact direction

- workflow outputs should end up in MinIO
- dataset snapshots may live in MinIO if needed later
- per-run Kubernetes PVCs are not the intended long-term artifact pattern

## Local PV versus shared storage

### Static local PVs

Advantages:

- matches the current cluster and the existing v1 operational pattern
- keeps node affinity explicit
- does not require operating a CSI stack immediately

Tradeoffs:

- service rescheduling is node-bound
- node loss requires operator restore work
- backups remain an operator responsibility

### Shared or CSI-backed storage

Advantages:

- easier pod mobility
- clearer future path for additional stateful services

Tradeoffs:

- introduces a new cluster primitive to operate
- should not be made the default until it is intentionally chosen, tested, and documented

## Expected internal DNS names

- `glasslab-workflow-api.glasslab-v2.svc.cluster.local`
- `glasslab-postgres.glasslab-v2.svc.cluster.local`
- `glasslab-nats.glasslab-v2.svc.cluster.local`
- `glasslab-minio.glasslab-v2.svc.cluster.local`
