# Stateful Object Inventory 2026-04

This document is the authoritative stateful-object inventory for Glasslab v2.

It classifies stateful objects into:

- records
- files/objects
- secrets
- ephemeral runtime/cache

The goal is to remove ambiguity about what the platform is actually persisting
and where that persistence should live.

## Confidence Levels

- `validated live`: confirmed from `.44` during recent work
- `repo contract`: committed manifests or code defaults
- `documented live`: stated in current docs but not freshly rechecked in this pass
- `historical`: retained for migration context only

## Category Rules

### Records

System-of-record metadata that should live in Postgres.

### Files/Objects

Durable artifact or source-document bytes that should live in MinIO or shared
filesystem.

### Secrets

Sensitive values that should live only in Kubernetes Secrets and encrypted `.44`
backup artifacts.

### Ephemeral Runtime/Cache

Reconstructable pod-local or runtime-local state that is not the long-term
system of record.

## Inventory

| Object | Category | Owner service | Current location | Durability expectation | Confidence |
|---|---|---|---|---|---|
| Research sessions | Record | `workflow-api` | Postgres `workflow_state` | Durable | `validated live` |
| Stage records | Record | `workflow-api` | Postgres `workflow_state` | Durable | `validated live` |
| Source-document metadata | Record | `workflow-api` | Postgres `workflow_state` | Durable | `validated live` |
| Design drafts | Record | `workflow-api` | Postgres `workflow_state` | Durable | `validated live` |
| Run metadata | Record | `workflow-api` | Postgres `workflow_state` | Durable | `validated live` |
| Decisions / campaign lineage | Record | `workflow-api` | Postgres `workflow_state` | Durable | `validated live` |
| Schedule records | Record | `workflow-api` | Postgres `workflow_state` | Durable | `documented live` |
| Comparison records / summaries refs | Record | `workflow-api` / evaluator integration | Postgres target, exact shape still evolving | Durable | `repo contract` |
| Workflow registry definitions | Record-like config | `workflow-registry` | Git-tracked definitions in repo | Durable by Git, not runtime DB state | `repo contract` |
| Source-document blobs | File/Object | `workflow-api` | `/mnt/artifacts/source-documents` by default; MinIO supported | Durable | `repo contract` |
| Run artifact bundles | File/Object | Runner + `workflow-api` + reporter | `/mnt/artifacts/<run_id>/` on shared artifacts path | Durable | `repo contract` |
| Logs | File/Object | Executor / runner wrapper | `logs/` within run bundle | Durable enough for operator debugging | `repo contract` |
| Reports (`report.md`, summaries) | File/Object | reporter | Run artifact bundle / artifact store | Durable | `repo contract` |
| Notebooks / presentation artifacts | File/Object | reporter / workload-specific step | Run artifact bundle / artifact store | Optional durable | `repo contract` |
| Checkpoints | File/Object | workload runner | Artifact store | Durable for training workloads | `repo contract` |
| Embeddings / prediction dumps | File/Object | workload runner | Artifact store | Durable when produced | `repo contract` |
| Shared datasets | File/Object | workload runners | `/mnt/datasets` via `glasslab-shared-datasets` PVC | Durable shared file plane | `repo contract` |
| Postgres data | File/Object backing a DB | `glasslab-postgres` | `glasslab-postgres-data` -> `/var/lib/glasslab-v2/postgres` on `node01` | Durable | `validated live` |
| MinIO object data | File/Object backing object store | `glasslab-minio` | `glasslab-minio-data` -> `/var/lib/glasslab-v2/minio` on `node01` | Durable | `documented live` |
| NATS JetStream data | File/Object backing message store | `glasslab-nats` | `glasslab-nats-data` -> `/var/lib/glasslab-v2/nats` on `node05` | Durable enough for single-node target | `documented live` |
| Postgres credentials | Secret | `glasslab-postgres` consumers | Kubernetes Secret from `.44` local manifest | Durable via secret backup, not Git | `validated live` |
| MinIO credentials | Secret | `glasslab-minio` and clients | Kubernetes Secret from `.44` local manifest | Durable via secret backup, not Git | `documented live` |
| GHCR pull secret | Secret | Cluster workloads | `glasslab-ghcr-pull` secret | Durable via cluster secret management | `documented live` |
| WhatsApp gateway token / related gateway secrets | Secret | `glasslab-whatsapp-gateway` | Kubernetes Secret from `.44` local manifest | Durable via secret backup, not Git | `documented live` |
| External API keys used by workloads | Secret | Relevant service | Kubernetes Secret / `.44` local manifest | Durable via secret backup, not Git | `repo contract` |
| Unpacked runtime bundles | Ephemeral runtime/cache | Service-specific runtime | `emptyDir` or pod-local filesystem | Reconstructable | `repo contract` |
| Temporary job scratch space | Ephemeral runtime/cache | Kubernetes Job / runner | pod-local writable filesystem | Reconstructable | `repo contract` |
| Pod-local caches | Ephemeral runtime/cache | workload containers | pod-local filesystem | Reconstructable | `repo contract` |
| Transient staging directories | Ephemeral runtime/cache | service or runner | pod-local filesystem | Reconstructable | `repo contract` |
| Historical JSON workflow store | Historical record path | `workflow-api` legacy path | old `run-store.json` on shared artifacts path | Backup/import only, not active record store | `validated live` |
| Historical OpenClaw state | Historical secret/file path | removed service | removed from live cluster; old docs only | Historical only | `historical` |

## Current Boundary Statement

The intended and now mostly-real boundary is:

- Postgres owns records
- shared filesystem and/or MinIO own files
- Secrets live outside Git and must be backed up from `.44`
- ephemeral runtime state is disposable

## Remaining Ambiguities To Resolve

These are still not crisp enough:

1. Source-document blobs
- current default is filesystem-backed on the shared artifacts plane
- MinIO support exists
- the near-term canonical choice should be stated more sharply

2. Artifact byte plane
- current contract still permits shared filesystem as the active artifact path
- MinIO is the intended durable direction
- the migration boundary is not fully closed yet

3. Comparison/evaluator persisted records
- the artifact outputs are clear
- the exact Postgres persistence shape for comparison summaries is still evolving

## Rules Going Forward

1. No system-of-record workflow state on the shared artifacts filesystem.
2. No secrets in Git.
3. No workload should rely on pod-local scratch as durable state.
4. Every new workload must state:
- which records it adds
- which files it emits
- which secrets it requires
- which temporary paths it uses

## Practical Reading

If a future feature needs persistence, ask first:

1. Is this a record?
- Put it in Postgres.

2. Is this a file/object?
- Put it in MinIO or the shared file plane.

3. Is this a secret?
- Put it in a Kubernetes Secret and `.44` encrypted backup scope.

4. Is this reconstructable scratch?
- Keep it ephemeral.
