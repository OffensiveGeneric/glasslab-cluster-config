# Storage

This directory holds future durable-storage manifests for Glasslab v2.

Current policy:

- do not assume a cluster-wide default `StorageClass`
- prefer explicit, reviewable PV/PVC wiring for the first durable v2 step
- follow the existing v1 local-PV pattern before introducing a shared CSI dependency

Current example:

- `10-static-local-pv.example.yaml`: static local PV/PVC pattern for Postgres and MinIO

Do not apply these examples unchanged. Pick the target node paths and capacity plan first.
