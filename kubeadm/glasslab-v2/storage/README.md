# Storage

This directory holds future durable-storage manifests for Glasslab v2.

Current policy:

- do not assume a cluster-wide default `StorageClass`
- prefer explicit, reviewable PV/PVC wiring for the first durable v2 step
- follow the existing v1 local-PV pattern before introducing a shared CSI dependency

Current tracked manifests:

- `10-static-local-pv.example.yaml`: example static local PV/PVC pattern
- `10-static-local-pv.yaml`: current static local PV/PVC wiring for Postgres, MinIO, and NATS
- `20-nfs-static-pv.yaml`: shared NFS-backed RWX PV/PVC wiring for datasets and artifacts
- `90-nfs-smoke-test.yaml`: one-shot validation pod for the NFS-backed PVCs

The current live durable-storage plan is:

- `glasslab-postgres-data` on `node01` at `/var/lib/glasslab-v2/postgres`
- `glasslab-minio-data` on `node01` at `/var/lib/glasslab-v2/minio`
- `glasslab-nats-data` on `node05` at `/var/lib/glasslab-v2/nats`

The current tracked shared-storage plan is:

- NFS server `192.168.1.207`
- export root `/volume1/backup`
- `glasslab-shared-datasets` backed by `/volume1/backup/glasslab-v2/shared-datasets`
- `glasslab-shared-artifacts` backed by `/volume1/backup/glasslab-v2/shared-artifacts`

State ownership:

- Postgres owns workflow records and pgvector-backed semantic indexes.
- The `.207` shared artifacts PVC owns large run outputs, logs, reports,
  notebooks, source blobs, and other large files.
- Workload containers should write completed bundles under
  `/mnt/artifacts/{run_id}`; `workflow-api` stores references and summaries in
  Postgres.
