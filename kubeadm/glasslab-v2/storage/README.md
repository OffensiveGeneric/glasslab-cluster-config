# Storage

This directory holds future durable-storage manifests for Glasslab v2.

Current policy:

- do not assume a cluster-wide default `StorageClass`
- prefer explicit, reviewable PV/PVC wiring for the first durable v2 step
- follow the existing v1 local-PV pattern before introducing a shared CSI dependency

Current tracked manifests:

- `10-static-local-pv.example.yaml`: example static local PV/PVC pattern
- `10-static-local-pv.yaml`: current node01-backed static local PV/PVC wiring for Postgres and MinIO

The current live durable-storage plan is:

- `glasslab-postgres-data` on `node01` at `/var/lib/glasslab-v2/postgres`
- `glasslab-minio-data` on `node01` at `/var/lib/glasslab-v2/minio`
- `glasslab-openclaw-state` on `node01` at `/var/lib/glasslab-v2/openclaw-state`
