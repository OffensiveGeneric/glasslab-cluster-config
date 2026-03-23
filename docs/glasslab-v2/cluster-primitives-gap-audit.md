# Cluster Primitives Gap Audit

Date: 2026-03-16

This document records the remaining infrastructure primitives Glasslab v2 still needs after the first live backend and OpenClaw validation pass.

## Current state

- `glasslab-v2` is live on the cluster. Postgres, NATS, MinIO, and `workflow-api` are healthy.
- OpenClaw has been validated live as an internal-only service, but the committed Deployment manifest still defaults to `replicas: 0` so a raw manifest apply does not auto-enable it.
- The cluster has no `StorageClass`.
- `glasslab-v2` now has explicit PVCs for `Postgres`, `MinIO`, and OpenClaw writable state, all backed by static local PVs on `node01`.
- `glasslab-v2` now also has an explicit PVC for NATS JetStream data, backed by a static local PV on `node05`.
- All Glasslab v2 Services are `ClusterIP`. No `Ingress` objects exist in the cluster.
- `workflow-api` now targets a private GHCR image pull path via the in-cluster `glasslab-ghcr-pull` secret and has been revalidated live on `node05`.
- Real v2 secret manifests exist only as ignored local files on `.44` under `kubeadm/glasslab-v2/secrets/*.local.yaml`.
- The repo snapshots tracked provisioner PXE/autoinstall config under `live-config/provisioner/`.
- Most tracked autoinstall profiles already enforce key-only SSH, but legacy password material still exists in tracked provisioning snapshots.

## Risks and missing primitives

### Durable storage

- `workflow-api` is stateless enough for the current loop.
- `Postgres` and `MinIO` are now on explicit retained local PV/PVC storage and no longer depend on `emptyDir`.
- OpenClaw state and session data are now on explicit retained local PV/PVC storage and survive pod replacement on `node01`.
- NATS is running with JetStream enabled on an explicit retained local PV/PVC on `node05`, which is sufficient for the current single-node durability target.
- The cluster still has no shared or default storage strategy beyond the new explicit local PVs.

### Internal service exposure

- Current access is safe-by-default because everything is `ClusterIP`, but the steady-state access pattern is still implicit.
- `kubectl port-forward` is doing too much work today: smoke tests, operator checks, and service admin access all assume it.
- There is no declared internal ingress or reverse-proxy path for OpenClaw, MinIO console, or optional MLflow.

### Image distribution

- `workflow-api` now uses a private GHCR pull path with the in-cluster `glasslab-ghcr-pull` secret and no longer depends on node-local import or `node03` pinning.
- `workflow-api` no longer depends on `node03`-local image import and can reschedule onto other workers that can reach GHCR.
- OpenClaw currently uses `ghcr.io/openclaw/openclaw:latest`; that is acceptable for validation, but not as a long-term pinning strategy.

### Secrets durability and disaster recovery

- The committed repo intentionally excludes live v2 secret values.
- `scripts/snapshot-provisioner-config.sh` does not back up ignored secret manifests.
- A loss of `.44` without a separate encrypted backup would require password/token rotation and manual reconstruction.

### PXE and autoinstall cleanup

- The historical `clusteradmin` password injection has been removed from the tracked `node48` profile.
- The tracked cloud-init profiles now use rotated non-shared placeholder hashes in `identity.password`, but the live provisioner still needs to be re-snapshotted after the same cleanup is applied on `.44`.
- The reviewed wrapper-based maintenance sudo path now exists in the repo and has been deployed live to the worker nodes, which removes the earlier helper-side blocker to PXE cleanup.

## Recommended next actions

1. Keep the cluster-wide default `StorageClass` unset until a shared storage backend is deliberately chosen and documented.
2. Keep backend services `ClusterIP` only and standardize internal-only access rules in repo docs before adding any ingress controller.
3. Keep the private GHCR pull path healthy and reuse it for the next custom Glasslab images so `.44`-local imports stop being the default pattern.
4. Keep the encrypted off-host backup procedure for `.44`-local secret manifests as a required deploy dependency.
5. Apply the same password-material cleanup on the live provisioner, then snapshot `.44` back into `live-config/provisioner`.

## Deferred items

- Shared CSI-backed storage and a cluster-wide default `StorageClass` are future work, not a blocker for the first durable v2 step.
- Internal ingress or reverse-proxy standardization is future work after the access model is agreed. It is not required for the current internal-only deployment.
- A stable control-plane endpoint or VIP is only needed if the lab moves to an HA control plane. It is not a blocker for the current single-control-plane cluster.
