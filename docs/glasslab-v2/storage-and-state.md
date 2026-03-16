# Storage And State

Glasslab v2 needs three explicit platform primitives before it becomes a durable workflow system.

## Postgres

Postgres is the system of record for run state, workflow requests, approval decisions, and queue history. The initial manifest keeps the deployment shape explicit but uses `emptyDir` so the stack can be brought up before static persistent volumes are chosen.

## MinIO

MinIO is the object store for artifact bundles, reports, and optional dataset snapshots. The first manifest is intentionally internal-only and also starts with `emptyDir` for smoke-test bring-up.

## NATS

NATS is the internal event bus for status changes, notifications, and later background workers. It stays stateless enough for the first deployment slice.

## Current storage posture

The cluster does not have a `StorageClass` today. To keep v2 readable and incrementally deployable, the initial manifests use `emptyDir` where durable storage will eventually be required. Replace those volumes with static local PV or PVC wiring before treating Postgres or MinIO data as durable.

## Expected internal DNS names

- `glasslab-workflow-api.glasslab-v2.svc.cluster.local`
- `glasslab-postgres.glasslab-v2.svc.cluster.local`
- `glasslab-nats.glasslab-v2.svc.cluster.local`
- `glasslab-minio.glasslab-v2.svc.cluster.local`
