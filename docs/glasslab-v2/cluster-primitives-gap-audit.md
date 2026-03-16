# Cluster Primitives Gap Audit

Date: 2026-03-16

This document records the remaining infrastructure primitives Glasslab v2 still needs after the first live backend and OpenClaw validation pass.

## Current state

- `glasslab-v2` is live on the cluster. Postgres, NATS, MinIO, and `workflow-api` are healthy.
- OpenClaw has been validated live as an internal-only service, but the committed Deployment manifest still defaults to `replicas: 0` so a raw manifest apply does not auto-enable it.
- The cluster has no `StorageClass` and `glasslab-v2` currently has no PVCs.
- Postgres, MinIO, NATS, and OpenClaw writable state use `emptyDir`.
- All Glasslab v2 Services are `ClusterIP`. No `Ingress` objects exist in the cluster.
- `workflow-api` is built on `.44`, imported into `node03` containerd, and pinned to `node03`.
- Real v2 secret manifests exist only as ignored local files on `.44` under `kubeadm/glasslab-v2/secrets/*.local.yaml`.
- The repo snapshots tracked provisioner PXE/autoinstall config under `live-config/provisioner/`.
- Most tracked autoinstall profiles already enforce key-only SSH, but legacy password material still exists in tracked provisioning snapshots.

## Risks and missing primitives

### Durable storage

- `workflow-api` is stateless enough for the current loop, but Postgres and MinIO are not durable today.
- NATS is running with JetStream enabled and an `emptyDir` volume. That is acceptable for short-lived development traffic, but not for durable queue or event retention.
- OpenClaw state and session data are ephemeral. That is acceptable for first validation, but not for durable operator history.
- The cluster has no default or explicit v2 storage plan beyond `emptyDir`.

### Internal service exposure

- Current access is safe-by-default because everything is `ClusterIP`, but the steady-state access pattern is still implicit.
- `kubectl port-forward` is doing too much work today: smoke tests, operator checks, and service admin access all assume it.
- There is no declared internal ingress or reverse-proxy path for OpenClaw, MinIO console, or optional MLflow.

### Image distribution

- `workflow-api` depends on a local build/import path on `.44` and is pinned to `node03`.
- This blocks clean failover or rescheduling to another node.
- The repo does not yet document a migration from manual `ctr import` to pull-based deployment.
- OpenClaw currently uses `ghcr.io/openclaw/openclaw:latest`; that is acceptable for validation, but not as a long-term pinning strategy.

### Secrets durability and disaster recovery

- The committed repo intentionally excludes live v2 secret values.
- `scripts/snapshot-provisioner-config.sh` does not back up ignored secret manifests.
- A loss of `.44` without a separate encrypted backup would require password/token rotation and manual reconstruction.

### PXE and autoinstall cleanup

- `live-config/provisioner/var/www/html/pxe/cloud-init/node48/user-data` still contains explicit `chpasswd` late-commands with the historical `clusteradmin` password.
- Current default and newer node profiles already disable password SSH, but the repo still tracks shared password hashes in the autoinstall `identity.password` field.
- Current helper scripts such as `scripts/build-import-workflow-api-image.sh` and `scripts/sync-titanic-dataset.sh` still assume a node sudo password may be needed, so full cleanup is not yet a safe one-line change.

## Recommended next actions

1. Replace v2 `emptyDir` storage for Postgres and MinIO with explicit static local PV/PVC wiring under `kubeadm/glasslab-v2/storage/`.
2. Keep the cluster-wide default `StorageClass` unset until a shared storage backend is deliberately chosen and documented.
3. Keep backend services `ClusterIP` only and standardize internal-only access rules in repo docs before adding any ingress controller.
4. Publish custom v2 images to a pullable registry or internal registry mirror, then remove the `node03` pin from `workflow-api`.
5. Add an encrypted off-host backup procedure for `.44`-local secret manifests and treat it as a required deploy dependency.
6. Replace password-dependent node maintenance helpers before purging the remaining PXE/autoinstall password material from tracked config.

## Deferred items

- Shared CSI-backed storage and a cluster-wide default `StorageClass` are future work, not a blocker for the first durable v2 step.
- Internal ingress or reverse-proxy standardization is future work after the access model is agreed. It is not required for the current internal-only deployment.
- A stable control-plane endpoint or VIP is only needed if the lab moves to an HA control plane. It is not a blocker for the current single-control-plane cluster.
