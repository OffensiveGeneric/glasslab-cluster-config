# State And Storage Map 2026-03-27

Status: mixed historical note with a current-state override.

This file was originally written when `workflow-api` still used the JSON store
on the shared artifacts PVC. As of the 2026-04-22 rollout, the live
`workflow-api` store backend is now `postgres`, with the prior JSON store
imported into Postgres from `.44`.

Use this file for the broad storage map, but do not rely on its older JSON-store
details without checking the current override below.

This note is the current high-signal answer to:

- where research-session state lives
- where fetched papers and source documents live
- where run artifacts live
- where OpenClaw keeps chat and WhatsApp state
- where secrets and images live

It is meant to reduce the recurring confusion between:

- repo-declared paths
- documented live state
- actual live state validated from `.44`

## Scope And Confidence

Three confidence levels are used below:

- `validated live`: checked from `.44` during recent work
- `repo contract`: committed manifests or code defaults
- `.44 local only`: depends on ignored local files or live cluster objects that are not committed

## Primary Research State

### Research sessions and stage metadata

What it contains:

- research sessions
- research problems
- paper-intake queues
- source-document metadata
- intakes
- interpretations
- assessments
- design drafts
- runs
- schedules
- schedule executions
- session memory:
  - working notes
  - decision log
  - next experiment ideas

Current live backend:

- `validated live`
- `workflow-api` now runs with:
  - `GLASSLAB_WORKFLOW_API_STORE_BACKEND=postgres`
  - `GLASSLAB_WORKFLOW_API_STORE_POSTGRES_DSN` from the local workflow-api secret on `.44`

Current live location:

- `validated live`
- Postgres table:
  - `workflow_state`
- current imported store row:
  - `store_key='default'`

Backing storage:

- `validated live`
- Postgres StatefulSet:
  - `glasslab-postgres`
- PVC:
  - `glasslab-postgres-data`
- local PV path on `node01`:
  - `/var/lib/glasslab-v2/postgres`

Important implication:

- research-session state is no longer ephemeral pod memory
- the live source of truth for session/stage metadata is now Postgres
- the old JSON file on the shared artifacts PVC is now a backup/import source, not the active record store

## Literature And Paper Storage

### Source-document metadata

What it contains:

- `SourceDocumentRecord`
- source URL
- content type
- title
- sha256
- size
- session attachment
- extracted text excerpt

Current metadata store:

- `validated live`
- source-document metadata now lives in the same Postgres-backed workflow store as the rest of the session/stage records

### Source-document blobs

What it contains:

- fetched PDFs
- fetched HTML
- extracted text sidecars when written as files

Current default storage mode:

- `repo contract`
- `GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_STORAGE_MODE=filesystem`
- default path:
  - `/mnt/artifacts/source-documents`

Alternate supported mode:

- `repo contract`
- `GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_STORAGE_MODE=minio`
- bucket:
  - `research-sources`

Current practical answer:

- the committed default is filesystem-backed source documents on the shared artifacts PVC
- MinIO support exists in code, but should not be treated as the default active source-document store unless revalidated live

## Run Artifacts And Logs

### Run outputs

What it contains:

- `status.json`
- `artifacts_index.json`
- logs
- reports
- workflow-specific output files
- runner-produced files such as:
  - metrics
  - notebooks
  - training contracts

Current path contract:

- `repo contract`
- `workflow-api` uses:
  - `GLASSLAB_WORKFLOW_API_ARTIFACTS_MOUNT_PATH=/mnt/artifacts`
- run artifact root:
  - `/mnt/artifacts/<run_id>/`

Backing storage:

- `repo contract`
- shared RWX PVC:
  - `glasslab-shared-artifacts`
- NFS export:
  - `192.168.1.207:/volume1/backup/glasslab-v2/shared-artifacts`

Important implication:

- run artifacts and source-document blobs still share the shared artifacts PVC
- workflow metadata no longer uses that same PVC as the active record store
- the storage split is now closer to the intended model:
  - Postgres for records
  - shared artifacts path for files

## Datasets

### Shared datasets

Current contract:

- `repo contract`
- PVC:
  - `glasslab-shared-datasets`
- mount path in jobs:
  - `/mnt/datasets`
- backing export:
  - `192.168.1.207:/volume1/backup/glasslab-v2/shared-datasets`

Current use:

- bounded runs and future CV/GPU runs are expected to read datasets from this shared RWX path

## OpenClaw State

### OpenClaw runtime bundle

What it is:

- exported config and workspaces
- generated `openclaw.json`
- prompt/binding/plugin runtime payload

Current location:

- `repo contract`
- mounted into the pod as:
  - ConfigMap `glasslab-openclaw-config`
- unpacked by init container into:
  - `/var/lib/openclaw/runtime`

Durability:

- runtime unpack destination is `emptyDir`
- the generated runtime bundle is reconstructed on pod start
- this is fine for generated runtime, but it is not where credentials or session history should live

### OpenClaw persistent state

What it contains:

- WhatsApp credentials
- OpenClaw agent/session state
- auth profiles
- operator session transcripts
- plugin scratch state

Current mount:

- `repo contract`
- `OPENCLAW_STATE_DIR=/var/lib/openclaw/state`
- PVC:
  - `glasslab-openclaw-state`

Backing storage:

- `repo contract`
- retained local PV on `node01`
- path:
  - `/var/lib/glasslab-v2/openclaw-state`

Important subpaths:

- WhatsApp credentials:
  - `/var/lib/openclaw/state/credentials/whatsapp/default`
- operator sessions:
  - `/var/lib/openclaw/state/agents/operator/sessions`
- operator auth profiles:
  - `/var/lib/openclaw/state/agents/operator/agent/auth-profiles.json`
- main agent auth profiles:
  - `/var/lib/openclaw/state/agents/main/agent/auth-profiles.json`
- workflow-api-tool scratch state:
  - `/var/lib/openclaw/state/workflow-api-tool`

## Recent Failure Modes

These are high-value operational notes because they look similar from chat, but they have very different causes.

### 1. Backend healthy, OpenClaw plugin broken

Observed live during the March 27-28 work:

- `workflow-api` remained healthy
- WhatsApp transport remained healthy
- but the `workflow-api-tool` plugin failed to load inside OpenClaw due to a runtime parse error

Symptoms in chat:

- OpenClaw claimed backend actions were unavailable or unreachable
- allowed tool names appeared in the prompt, but none of them could actually run

Where to confirm:

- OpenClaw pod logs:
  - plugin load errors for
    - `/var/lib/openclaw/runtime/glasslab-config/plugins/workflow-api-tool/index.ts`

Important implication:

- a broken OpenClaw runtime plugin can make the whole backend appear down from chat
- this is not the same failure as a dead `workflow-api` service

### 2. Backend healthy, tool timeout too small

Observed live during literature-harvest testing:

- `workflow-api` successfully created paper-intake queues
- but OpenClaw timed out waiting for the result and described that as backend failure

Symptoms in logs:

- OpenClaw:
  - tool timeout / aborted operation
- `workflow-api`:
  - successful `201 Created` on paper-intake queue routes

Important implication:

- slow literature harvest and real backend outages must be debugged differently
- the correct checks are:
  - OpenClaw pod logs
  - `workflow-api` pod logs
  - live runtime provenance and runtime config

### 3. Repo state and live runtime can diverge

Observed repeatedly during the March 27 work:

- laptop repo state was correct
- `.44` source tree was older
- or `.44` exporter script was older
- or the live runtime bundle was older than the repo

Important implication:

- live behavior must be treated as a separate truth surface from committed code
- provenance fields and explicit `.44` sync steps are not optional niceties; they are required debugging tools

Important implication:

- OpenClaw state is durable across pod replacement
- it is still node-local to `node01`, not shared/failover-grade

## Postgres, MinIO, And NATS

These are still core backend stateful services even though the current research-session path is not yet using Postgres for session metadata.

### Postgres

- `repo contract`
- local PV on `node01`
- host path:
  - `/var/lib/glasslab-v2/postgres`

### MinIO

- `repo contract`
- local PV on `node01`
- host path:
  - `/var/lib/glasslab-v2/minio`

Current relevance:

- intended object storage home for artifacts and source documents later
- not currently the authoritative store for session metadata

### NATS

- `repo contract`
- local PV on `node05`
- host path:
  - `/var/lib/glasslab-v2/nats`

## Secrets

### Cluster secret manifests

Current source of truth:

- `.44 local only`
- ignored local files under:
  - `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml`
  - `kubeadm/glasslab-v2/secrets/20-minio.local.yaml`
  - `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`

Important implication:

- Git is not enough to reconstruct live secrets
- `.44` local secret backup and DR remains mandatory

### What OpenClaw secret material drives

Current deployment contract includes:

- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_VLLM_API_KEY`
- `OPENCLAW_OLLAMA_API_KEY`
- `OPENCLAW_WHATSAPP_OWNER`

## Images

### Custom Glasslab images

Current intended source of truth:

- private GHCR packages

Current relevant images:

- `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.26-local`
- `ghcr.io/offensivegeneric/glasslab-tabular-runner:0.1.2`
- `ghcr.io/offensivegeneric/glasslab-literature-runner:0.1.2`
- `ghcr.io/offensivegeneric/glasslab-gpu-experiment-runner:0.1.1`

Cluster pull path:

- namespace secret:
  - `glasslab-ghcr-pull`

Important implication:

- the primary image distribution path is now pull-based GHCR
- node-local image import on `.44` is a break-glass fallback, not the intended steady state

## What This Means For The Research Workflow

If you ask:

- where does the conversation-backed research state live?

Current answer:

- in `workflow-api` JSON metadata at:
  - `/mnt/artifacts/workflow-api/state/run-store.json`

If you ask:

- where do fetched papers live?

Current answer:

- metadata in the JSON store
- blobs by default under:
  - `/mnt/artifacts/source-documents`

If you ask:

- where do experiment outputs live?

Current answer:

- under:
  - `/mnt/artifacts/<run_id>/`

If you ask:

- where does OpenClaw keep its memory and WhatsApp linkage?

Current answer:

- under:
  - `/var/lib/openclaw/state`
- backed by:
  - `glasslab-openclaw-state`
- on:
  - `node01`

## Current Risks

The biggest remaining storage/state risks are:

- `workflow-api` session metadata is durable, but still JSON-backed rather than Postgres-backed
- shared artifacts PVC is doing too many jobs at once
- source-document blobs are not yet clearly separated from run artifacts operationally
- OpenClaw state is durable but still node-local
- secrets still depend on `.44`-local ignored manifests

## Recommended Next Documentation Rule

When adding any new persistent object, document all three immediately:

1. logical owner
2. in-pod path or backend store
3. backing PVC / object bucket / local-secret path

If a change does not answer those three, the storage story is not done yet.
