# Backup And Restore For Local-PV-Backed Services

This runbook covers the first backup/restore path for the local-PV-backed Glasslab v2 services:

- Postgres on `node01`
- MinIO on `node01`
- NATS JetStream data on `node05`

These procedures are about surviving node-local disk loss or accidental service data loss before true multi-node failover exists.

## Backing Paths

Tracked local PV paths:

- Postgres: `/var/lib/glasslab-v2/postgres` on `node01`
- MinIO: `/var/lib/glasslab-v2/minio` on `node01`
- NATS: `/var/lib/glasslab-v2/nats` on `node05`

Tracked PVC names:

- `glasslab-postgres-data`
- `glasslab-minio-data`
- `glasslab-nats-data`

## Recommended Backup Cadence

- Postgres:
  - daily logical dump
  - weekly filesystem-level archive during a short maintenance window
- MinIO:
  - daily filesystem-level archive or bucket-level replication if that becomes available later
- NATS:
  - daily filesystem-level archive if JetStream state matters
  - extra backup before changing subjects/stream retention policy

Recommended off-host destination:

- the NFS-backed backup pool under `192.168.1.207:/volume1/backup/glasslab-v2/`

This runbook does not assume that destination is already mounted everywhere. It is the intended normal target, not a guaranteed current mountpoint.

## Recovery Scope

What these backups recover:

- Postgres:
  - database files or logical dumps
- MinIO:
  - object data and local metadata from the mounted path
- NATS:
  - JetStream data on disk

What they do not recover by themselves:

- Kubernetes manifests or repo history
- ignored `.44` local secret manifests
- node OS state
- cluster-wide service availability during a node loss event

Use this together with:

- `../secrets-and-dr.md`
- `restore-v2-secrets.md`

## Preferred Backup Pattern

Use a temporary pod that mounts the target PVC and creates a tar archive, then copy that archive off-host.

Why:

- does not require broad node sudo access
- works with the current local-PV posture
- keeps the backup procedure close to Kubernetes reality

## NATS Backup

Use the same temporary-pod pattern, but mount `glasslab-nats-data` on `node05`.

Minimal sequence:

1. if possible, stop writes briefly by scaling NATS down
2. mount `glasslab-nats-data` in a temporary pod on `node05`
3. archive `/mnt/nats`
4. copy the archive off-host
5. for restore, scale NATS down, extract the archive back into the mounted path, then scale back up

Important:

- this restores on-disk JetStream state
- it does not create HA or cross-node recovery by itself

## Postgres Backup

Preferred pattern:

1. take a logical backup first
2. optionally pair it with a filesystem-level archive during a quiet window

Logical backup example from the running pod:

```sh
kubectl -n glasslab-v2 exec glasslab-postgres-0 -- \
  sh -lc 'pg_dumpall -U "$POSTGRES_USER"' > postgres-$(date +%Y%m%d-%H%M%S).sql
```

Filesystem-level backup:

- mount `glasslab-postgres-data` in a temporary pod on `node01`
- create a tar archive of the data directory during a quiet window or with Postgres scaled down

Restore notes:

- logical restore is safer for service migration
- raw filesystem restore should only be done with Postgres stopped
- secrets must already be restored before the database pod is restarted

## MinIO Backup

MinIO currently sits on a retained local PV on `node01`.

Backup pattern:

1. mount `glasslab-minio-data` in a temporary pod on `node01`
2. archive the mounted data directory
3. copy the archive off-host

Restore notes:

- restore the data path before bringing the MinIO pod back
- this recovers the local object store contents
- it does not replace external bucket replication or versioned-object policy if those are added later

## Smallest Verified Drill

Verified on 2026-03-24:

- local-PV dry-restore pattern worked for a stateful service PVC
- archive extracted into a temporary restore directory inside the pod
- restored file listing confirmed expected files were present

## Restore Preconditions

Before restoring any service:

1. restore the relevant secret manifests if the service depends on ignored local secrets
2. ensure the target PVC still points at the expected node-local path
3. stop or scale down the service so it is not writing during restore
4. keep a copy of the damaged path until the restored service is verified

## Follow-Up Gaps

- no helper script exists yet for these service-specific backups
- Postgres logical backup scheduling is not yet automated
- MinIO and NATS still rely on operator-run backup cadence rather than built-in replication
- node-loss tolerance still needs the broader work tracked in issue `#13`
