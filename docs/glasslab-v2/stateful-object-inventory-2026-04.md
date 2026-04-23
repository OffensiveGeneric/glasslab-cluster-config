# Stateful Object Inventory 2026-04

This document is an audit of stateful objects in the Glasslab v2 cluster-config repository.

## Scope

This audit scans:
- `docs/glasslab-v2/`
- `services/`
- `kubeadm/glasslab-v2/`

And classifies every stateful object discovered.

## Classification Definitions

| Class | Definition |
|-------|-----------|
| **record** | Persistent logical record or metadata object stored in a database or registry |
| **file/object** | Physical file, binary blob, or object stored on filesystem/object storage |
| **secret** | Sensitive credential, token, key, or authentication material |
| **ephemeral cache/runtime scratch** | Temporary storage, logs, caches, or transient runtime state |

## Confidence Levels

| Level | Definition |
|-------|-----------|
| **repo contract** | Explicitly declared in committed manifests or code defaults |
| **documented live** | Validated live from `.44` and documented in operational docs |
| **unknown** | Referenced but not validated or documented |

---

## Inventory

### 1. Kubernetes Resources

#### 1.1 Namespace

| Name | Owner | Storage Location | Durability | Confidence |
|------|-------|------------------|------------|------------|
| `glasslab-v2` | Infrastructure | Kubernetes API | Cluster-scoped | repo contract |

**Owner**: Cluster infrastructure team  
**Storage Location**: Kubernetes API server  
**Durability Expectation**: Cluster-scoped; survives pod restarts  
**Confidence**: repo contract  
**Notes**: Base namespace for all Glasslab v2 workloads

---

#### 1.2 PersistentVolumes (PVs)

| Name | Owner | Storage Location | Durability | Confidence |
|------|-------|------------------|------------|------------|
| `glasslab-v2-postgres-data-pv` | Postgres | `/var/lib/glasslab-v2/postgres` on `node01` | Local disk, Retain | repo contract |
| `glasslab-v2-minio-data-pv` | MinIO | `/var/lib/glasslab-v2/minio` on `node01` | Local disk, Retain | repo contract |
| `glasslab-v2-nats-data-pv` | NATS | `/var/lib/glasslab-v2/nats` on `node05` | Local disk, Retain | repo contract |
| `glasslab-v2-shared-datasets-pv` | Shared Storage | `192.168.1.207:/volume1/backup/glasslab-v2/shared-datasets` | NFS RWX | repo contract |
| `glasslab-v2-shared-artifacts-pv` | Shared Storage | `192.168.1.207:/volume1/backup/glasslab-v2/shared-artifacts` | NFS RWX | repo contract |

**Owner**: Infrastructure team  
**Storage Location**: Node-local paths and NFS server  
**Durability Expectation**: Local PVs use Retain policy; NFS is managed externally  
**Confidence**: repo contract  
**Notes**: All local PVs are statically bound to specific nodes with explicit nodeAffinity

---

#### 1.3 PersistentVolumeClaims (PVCs)

| Name | Owner | Bound PV | Mount Path | Durability | Confidence |
|------|-------|----------|------------|------------|------------|
| `glasslab-postgres-data` | Postgres | `glasslab-v2-postgres-data-pv` | `/var/lib/postgresql/data` | Local disk (Retain) | repo contract |
| `glasslab-minio-data` | MinIO | `glasslab-v2-minio-data-pv` | `/data` | Local disk (Retain) | repo contract |
| `glasslab-nats-data` | NATS | `glasslab-v2-nats-data-pv` | `/data` | Local disk (Retain) | repo contract |
| `glasslab-shared-datasets` | Shared Storage | `glasslab-v2-shared-datasets-pv` | `/mnt/datasets` (by jobs) | NFS RWX | repo contract |
| `glasslab-shared-artifacts` | Shared Storage | `glasslab-v2-shared-artifacts-pv` | `/mnt/artifacts` (by jobs) | NFS RWX | repo contract |

**Owner**: Infrastructure team  
**Storage Location**: Bound to specific PVs as above  
**Durability Expectation**: PVCs persist across pod restarts; shared PVCs enable multi-pod access |
**Confidence**: repo contract  
**Notes**: Postgres, MinIO, NATS use ReadWriteOnce; shared storage uses ReadWriteMany

---

#### 1.4 Secrets

| Name | Owner | Storage Location | Secret Keys | Durability | Confidence |
|------|-------|------------------|-------------|------------|------------|
| `glasslab-v2-postgres` | Postgres | Kubernetes Secret API | POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD | In-cluster API | documented live |
| `glasslab-v2-minio` | MinIO | Kubernetes Secret API | MINIO_ROOT_USER, MINIO_ROOT_PASSWORD | In-cluster API | documented live |
| `glasslab-v2-workflow-api` | Workflow API | Kubernetes Secret API | GLASSLAB_WORKFLOW_API_STORE_POSTGRES_DSN | In-cluster API | documented live |
| `glasslab-whatsapp-gateway` | WhatsApp Gateway | Kubernetes Secret API | WHATSAPP_OWNER, WHATSAPP_ALLOW_FROM | In-cluster API | documented live |
| `glasslab-ghcr-pull` | Image Distribution | Kubernetes Secret API | Docker config (GHCR credentials) | In-cluster API | documented live |

**Owner**: Infrastructure team  
**Storage Location**: Kubernetes API (namespace-scoped)  
**Durability Expectation**: Non-committed; managed via `.44` local secret manifests  
**Confidence**: documented live  
**Notes**: 
- Secret values are NOT committed to Git (intentional)
- Local secret manifests on `.44` are the authoritative source
- Backup/restore documented in `runbooks/restore-v2-secrets.md`

---

#### 1.5 ConfigMaps

| Name | Owner | Storage Location | Keys | Durability | Confidence |
|------|-------|------------------|------|------------|------------|
| `glasslab-v2-workflow-api-config` | Workflow API | Kubernetes API | 25+ keys (workflow config, stage agent URLs, paths) | In-cluster API | repo contract |
| `glasslab-openclaw-config` | OpenClaw (historical) | Kubernetes API | Runtime bundle config | In-cluster API | repo contract |

**Owner**: Workflow API team  
**Storage Location**: Kubernetes API  
**Durability Expectation**: In-cluster; survives pod restarts  
**Confidence**: repo contract  
**Notes**: 
- Configures storage paths, agent URLs, execution modes
- `GLASSLAB_WORKFLOW_API_STORE_BACKEND` determines metadata store (memory/json/postgres)

---

#### 1.6 PriorityClasses

| Name | Owner | Value | Description | Durability | Confidence |
|------|-------|-------|-------------|------------|------------|
| `glasslab-user-high` | Infrastructure | 100000 | User-submitted jobs | Cluster-scoped | repo contract |
| `glasslab-autonomous-low` | Infrastructure | 1000 | Background autonomous jobs | Cluster-scoped | repo contract |

**Owner**: Infrastructure team  
**Storage Location**: Kubernetes scheduler configuration  
**Durability Expectation**: Cluster-scoped scheduling priority  
**Confidence**: repo contract  

---

#### 1.7 ServiceAccounts & RBAC

| Name | Owner | Namespace | Roles | Durability | Confidence |
|------|-------|-----------|-------|------------|------------|
| `glasslab-workflow-api` | Workflow API | glasslab-v2 | Job submitter, PVC/secret reader, node/pod reader | Namespace-scoped | repo contract |
| `glasslab-workflow-api-preflight-reader` | Workflow API | cluster-wide | nodes, pods reader (cluster-scoped) | Cluster-scoped | repo contract |

**Owner**: Workflow API team  
**Storage Location**: Kubernetes RBAC API  
**Durability Expectation**: Cluster-scoped role bindings  
**Confidence**: repo contract  

---

#### 1.8 Deployments & StatefulSets

| Name | Owner | Image | Replicas | Node | Durability | Confidence |
|------|-------|-------|----------|------|------------|------------|
| `glasslab-postgres` | Database | postgres:16 | 1 | node01 | StatefulSet with PVC | repo contract |
| `glasslab-minio` | Storage | minio/minio:latest | 1 | node01 | Deployment with PVC | repo contract |
| `glasslab-nats` | Messaging | nats:2.10-alpine | 1 | node05 | Deployment with PVC (JetStream) | repo contract |
| `glasslab-workflow-api` | API | ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.94-local | 1 | node05 | Deployment with PVC | documented live |
| `glasslab-interpretation-agent` | Stage Agents | ghcr.io/offensivegeneric/glasslab-interpretation-agent:0.1.1 | 1 | ClusterIP | Deployment | documented live |
| `glasslab-intake-agent` | Stage Agents | ghcr.io/offensivegeneric/glasslab-intake-agent:0.1.0 | 1 | ClusterIP | Deployment | documented live |
| `glasslab-assessment-agent` | Stage Agents | ghcr.io/offensivegeneric/glasslab-assessment-agent:0.1.0 | 1 | ClusterIP | Deployment | documented live |
| `glasslab-design-agent` | Stage Agents | ghcr.io/offensivegeneric/glasslab-design-agent:0.1.0 | 1 | ClusterIP | Deployment | documented live |
| `glasslab-schedule-worker` | Unattended Ops | ghcr.io/offensivegeneric/glasslab-schedule-worker:0.1.0 | 1 | ClusterIP | Deployment | documented live |
| `glasslab-whatsapp-gateway` | Transport | ghcr.io/offensivegeneric/glasslab-whatsapp-gateway:0.1.5-local | 1 | node05 | Deployment with emptyDir | documented live |
| `glasslab-whatsapp-web-bridge` | Transport | ghcr.io/offensivegeneric/glasslab-whatsapp-web-bridge:0.1.2-local | 1 | node05 | Deployment with emptyDir | documented live |
| `glasslab-research-command-router` | Command Routing | ghcr.io/offensivegeneric/glasslab-research-command-router:0.1.11-local | 1 | node05 | Deployment | documented live |
| `glasslab-research-ingress` | Ingress | ghcr.io/offensivegeneric/glasslab-research-ingress:0.1.1 | 1 | ClusterIP | Deployment | documented live |

**Owner**: Multiple teams (API, Transport, Agents, Infrastructure)  
**Storage Location**: Kubernetes Deployments/StatefulSets API  
**Durability Expectation**: 
- StatefulSet (Postgres): Pod identity preserved, PVC retention
- Deployments: Ephemeral pods, PVC mounts for stateful services
- WhatsApp services: emptyDir for transient state, secrets for auth  
**Confidence**: 
- Postgres, MinIO, NATS: repo contract (K8s manifests)
- Stage agents and transport services: documented live  
**Notes**: 
- WhatsApp services use `emptyDir` for state (not durable across pod restart)
- Auth state for WhatsApp is seeded from `glasslab-whatsapp-web-auth` Secret

---

#### 1.9 Services

| Name | Owner | Port | ClusterIP | Durability | Confidence |
|------|-------|------|-----------|------------|------------|
| `glasslab-postgres` | Database | 5432 | Internal | Service API | repo contract |
| `glasslab-minio` | Storage | 9000 (API), 9001 (Console) | Internal | Service API | repo contract |
| `glasslab-nats` | Messaging | 4222 (client), 8222 (monitoring) | Internal | Service API | repo contract |
| `glasslab-workflow-api` | API | 8080 | Internal | Service API | repo contract |
| `glasslab-interpretation-agent` | Stage Agents | 8091 | Internal | Service API | documented live |
| `glasslab-intake-agent` | Stage Agents | 8090 | Internal | Service API | documented live |
| `glasslab-assessment-agent` | Stage Agents | 8092 | Internal | Service API | documented live |
| `glasslab-design-agent` | Stage Agents | 8093 | Internal | Service API | documented live |
| `glasslab-schedule-worker` | Unattended Ops | 8094 | Internal | Service API | documented live |
| `glasslab-whatsapp-gateway` | Transport | 8097 | Internal | Service API | documented live |
| `glasslab-whatsapp-web-bridge` | Transport | 8098 | Internal | Service API | documented live |
| `glasslab-research-command-router` | Command Routing | 8095 | Internal | Service API | documented live |
| `glasslab-research-ingress` | Ingress | 8096 | Internal | Service API | documented live |

**Owner**: Multiple teams  
**Storage Location**: Kubernetes Services API  
**Durability Expectation**: ClusterIP services are stable DNS entries  
**Confidence**: repo contract / documented live  

---

### 2. Database Records (Postgres)

The `workflow_state` table stores all Glasslab research session and workflow metadata.

#### 2.1 Record Types

| Record Type | Owner | Storage Path | Key Fields | Durability | Confidence |
|-------------|-------|--------------|------------|------------|------------|
| `ResearchSessionRecord` | Sessions | Postgres `workflow_state` | session_id, goal, status, latest_*_id | Durable Postgres | documented live |
| `ResearchProblemRecord` | Sessions | Postgres `workflow_state` | problem_id, problem_statement, priorities | Durable Postgres | documented live |
| `IntakeRecord` | Sessions | Postgres `workflow_state` | intake_id, raw_request, normalized_summary | Durable Postgres | documented live |
| `InterpretationRecord` | Sessions | Postgres `workflow_state` | interpretation_id, literature_state_summary, research_gaps | Durable Postgres | documented live |
| `ReplicabilityAssessmentRecord` | Sessions | Postgres `workflow_state` | assessment_id, recommendation, blocking_reasons | Durable Postgres | documented live |
| `DesignDraftRecord` | Sessions | Postgres `workflow_state` | design_id, workflow_id, method_spec | Durable Postgres | documented live |
| `RunRecord` | Sessions | Postgres `workflow_state` | run_id, workflow_id, manifest, status | Durable Postgres | documented live |
| `DatasetRecord` | Data | Postgres `workflow_state` | dataset_id, uri, modality, task_type | Durable Postgres | documented live |
| `TechniqueCatalogRecord` | Data | Postgres `workflow_state` | technique_id, name, aliases, python_packages | Durable Postgres | documented live |
| `SourceDocumentRecord` | Data | Postgres `workflow_state` | document_id, source_url, content_type, sha256 | Durable Postgres | documented live |
| `MethodologyDraftRecord` | Autoresearch | Postgres `workflow_state` | methodology_draft_id, campaign_id, status | Durable Postgres | documented live |
| `AutoresearchCampaignRecord` | Autoresearch | Postgres `workflow_state` | campaign_id, objective, max_iterations | Durable Postgres | documented live |
| `AutoresearchIterationRecord` | Autoresearch | Postgres `workflow_state` | iteration_id, run_id, decision | Durable Postgres | documented live |
| `AutoresearchDecisionRecord` | Autoresearch | Postgres `workflow_state` | decision_id, decision_type, rationale | Durable Postgres | documented live |
| `ScheduledOperationRecord` | Unattended Ops | Postgres `workflow_state` | schedule_id, operation_type, cron_expr | Durable Postgres | documented live |
| `ScheduledExecutionRecord` | Unattended Ops | Postgres `workflow_state` | execution_id, schedule_id, result_status | Durable Postgres | documented live |
| `OperationRecord` | Operations | Postgres `workflow_state` | operation_id, operation_type, status | Durable Postgres | documented live |

**Owner**: Workflow API team  
**Storage Location**: Postgres database in `glasslab-v2` namespace  
**Durability Expectation**: Durable via PVC-backed StatefulSet  
**Confidence**: documented live  
**Notes**: 
- `store_key='default'` holds the entire serialized state
- Live backend: `GLASSLAB_WORKFLOW_API_STORE_BACKEND=postgres`
- Historical backup path: JSON file on shared artifacts (now imported)

---

### 3. File / Object Storage

#### 3.1 MinIO Buckets (Object Store)

| Bucket | Owner | Content | Durability | Confidence |
|--------|-------|---------|------------|------------|
| `research-sources` | Literature | Source document blobs (PDFs, HTML, extracted text) | MinIO local PV | repo contract |

**Owner**: Literature pipeline  
**Storage Location**: MinIO bucket on `/data` (local PV)  
**Durability Expectation**: Single-instance durability (no HA yet)  
**Confidence**: repo contract  
**Notes**: 
- Optional storage mode for source documents
- Configurable via `GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_STORAGE_MODE=minio`

---

#### 3.2 Shared Artifacts (NFS)

| Path | Owner | Content | Durability | Confidence |
|------|-------|---------|------------|------------|
| `/mnt/artifacts/<run_id>/` | Runs | Run outputs, logs, reports, artifacts_index.json | NFS RWX | repo contract |
| `/mnt/artifacts/workflow-api/state/run-store.json` | Workflow API | Historical JSON session store (imported) | NFS RWX | repo contract |
| `/mnt/artifacts/source-documents/` | Literature | Source document blobs (filesystem mode) | NFS RWX | repo contract |

**Owner**: Workflow API team  
**Storage Location**: NFS export `192.168.1.207:/volume1/backup/glasslab-v2/shared-artifacts`  
**Durability Expectation**: Shared read/write across nodes via NFSv4.1  
**Confidence**: repo contract  
**Notes**: 
- Primary storage for run artifacts
- Historical JSON store (now imported to Postgres)

---

#### 3.3 Shared Datasets (NFS)

| Path | Owner | Content | Durability | Confidence |
|------|-------|---------|------------|------------|
| `/mnt/datasets/` | Jobs | Training/inference datasets | NFS RWX | repo contract |

**Owner**: Job execution  
**Storage Location**: NFS export `192.168.1.207:/volume1/backup/glasslab-v2/shared-datasets`  
**Durability Expectation**: Shared read/write across nodes via NFSv4.1  
**Confidence**: repo contract  
**Notes**: Used by GPU/CV runs and batch executions

---

### 4. Service-Specific State

#### 4.1 WhatsApp Gateway

| State Type | Owner | Storage Location | Durability | Confidence |
|------------|-------|------------------|------------|------------|
| Session transcripts | WhatsApp Gateway | `emptyDir` (pod-local) | Ephemeral | documented live |
| Sender-pinned session_id | WhatsApp Gateway | `emptyDir` (pod-local) | Ephemeral | documented live |
| Provider webhook dedupe | WhatsApp Gateway | In-memory (provider_message_id cache) | Ephemeral | documented live |

**Owner**: Transport team  
**Storage Location**: Pod-local `emptyDir` volume  
**Durability Expectation**: Ephemeral; reset on pod restart  
**Confidence**: documented live  
**Notes**: 
- State is NOT durable across pod restarts
- Transcripts and sender sessions are rebuilt from WhatsApp provider
- Deduplication is in-memory only

---

#### 4.2 WhatsApp Web Bridge

| State Type | Owner | Storage Location | Durability | Confidence |
|------------|-------|------------------|------------|------------|
| Auth credentials | WhatsApp Web Bridge | `/var/lib/glasslab-whatsapp-web/default/creds.json` (emptyDir) | Ephemeral | documented live |
| Session state | WhatsApp Web Bridge | `/var/lib/glasslab-whatsapp-web/default/` | Ephemeral | documented live |

**Owner**: Transport team  
**Storage Location**: Pod-local `emptyDir` volume  
**Durability Expectation**: Ephemeral; reset on pod restart  
**Confidence**: documented live  
**Notes**: 
- Auth state seeded from `glasslab-whatsapp-web-auth` Secret
- State is NOT durable; requires re-authentication on restart

---

#### 4.3 Workflow API

| State Type | Owner | Storage Location | Durability | Confidence |
|------------|-------|------------------|------------|------------|
| Run metadata | Workflow API | Postgres `workflow_state` table | Durable | documented live |
| Run artifacts | Workflow API | `/mnt/artifacts/<run_id>/` | NFS | documented live |
| Source documents (filesystem mode) | Workflow API | `/mnt/artifacts/source-documents/` | NFS | documented live |
| Source documents (MinIO mode) | Workflow API | MinIO `research-sources` bucket | Object storage | repo contract |
| Workflow registry | Workflow API | `services/workflow-registry/definitions/*.json` | Git-backed | repo contract |
| Technique catalog | Workflow API | Postgres `workflow_state` (technique_catalog) | Durable | documented live |
| Digest schedules | Workflow API | Postgres `workflow_state` (schedules) | Durable | documented live |
| Approved rerun schedules | Workflow API | Postgres `workflow_state` (schedules) | Durable | documented live |

**Owner**: Workflow API team  
**Storage Location**: Postgres (metadata), NFS (files), Git (registry)  
**Durability Expectation**: Metadata durable via Postgres; files durable via NFS  
**Confidence**: documented live / repo contract  

---

#### 4.4 Autoresearch Campaigns

| State Type | Owner | Storage Location | Durability | Confidence |
|------------|-------|------------------|------------|------------|
| Campaign records | Autoresearch | Postgres `workflow_state` (autoresearch_campaigns) | Durable | documented live |
| Methodology drafts | Autoresearch | Postgres `workflow_state` (methodology_drafts) | Durable | documented live |
| Iteration records | Autoresearch | Postgres `workflow_state` (autoresearch_iterations) | Durable | documented live |
| Decision records | Autoresearch | Postgres `workflow_state` (autoresearch_decisions) | Durable | documented live |
| Notebook drafts | Autoresearch | `/mnt/artifacts/<campaign_id>/analysis_notebook.ipynb` | NFS | documented live |

**Owner**: Autoresearch pipeline  
**Storage Location**: Postgres (records), NFS (notebooks)  
**Durability Expectation**: Durable records, durable notebook artifacts  
**Confidence**: documented live  

---

### 5. Git-Backed State

#### 5.1 Workflow Registry

| Entry | Owner | Location | Status | Confidence |
|-------|-------|----------|--------|------------|
| `generic-tabular-benchmark` | Benchmarks | `services/workflow-registry/definitions/generic-tabular-benchmark.json` | ready (k8s) | repo contract |
| `literature-to-experiment` | Literature | `services/workflow-registry/definitions/literature-to-experiment.json` | ready (k8s) | repo contract |
| `gpu-experiment` | GPU/Research | `services/workflow-registry/definitions/gpu-experiment.json` | ready (k8s) | repo contract |
| `replication-lite` | Replication | `services/workflow-registry/definitions/replication-lite.json` | declared_only (unimplemented) | repo contract |

**Owner**: Workflow API team  
**Storage Location**: Git repository  
**Durability Expectation**: Immutable Git history  
**Confidence**: repo contract  

---

### 6. External Infrastructure

#### 6.1 NFS Server

| Resource | Location | Export | Purpose | Durability | Confidence |
|----------|----------|--------|---------|------------|------------|
| NFS Server | `192.168.1.207` | `/volume1/backup/glasslab-v2/shared-datasets` | Shared datasets | External | documented live |
| NFS Server | `192.168.1.207` | `/volume1/backup/glasslab-v2/shared-artifacts` | Shared artifacts | External | documented live |

**Owner**: Infrastructure team  
**Storage Location**: External NFS server  
**Durability Expectation**: External storage reliability  
**Confidence**: documented live  
**Notes**: Critical shared storage for runs and datasets

---

## Summary Statistics

| Category | Count | Durability Profile |
|----------|-------|-------------------|
| Kubernetes Namespaces | 1 | Cluster-scoped |
| PersistentVolumes | 5 | Local (Retain) or NFS |
| PersistentVolumeClaims | 5 | Bound to PVs |
| Secrets | 5 | In-cluster API (non-committed) |
| ConfigMaps | 2 | In-cluster API |
| PriorityClasses | 2 | Cluster-scoped |
| Deployments | 11 | Pod ephemeral, PVC-backed state |
| Services | 11 | ClusterIP, stable DNS |
| Database Records | 19+ | Postgres durable |
| MinIO Buckets | 1 | Object storage |
| Shared Filesystems | 2 | NFS RWX |
| Git-backed State | 4 | Immutable history |
| External Infrastructure | 1 | External reliability |

---

## Known Gaps

1. **WhatsApp services**: State is ephemeral (emptyDir); no durable session storage yet
2. **OpenClaw**: Historical state removed; not part of current inventory
3. **Secrets**: Not committed to Git; requires `.44` local backup
4. **HA**: No high-availability for local PV-backed services (Postgres, MinIO, NATS)

---

## Recovery Matrix Reference

| Service | Failure Domain | Recovery Strategy | Confidence |
|---------|---------------|-------------------|------------|
| Postgres | node01 loss | Backup/restore first | documented live |
| MinIO | node01 loss | Backup/restore first | documented live |
| NATS | node05 loss | Backup/restore first | documented live |
| WhatsApp Gateway | Pod restart | Re-authenticate, rebuild transcripts | documented live |
| WhatsApp Web Bridge | Pod restart | Re-authenticate, rebuild auth state | documented live |
| Workflow API | Pod restart | State retained in Postgres + NFS | documented live |
| Stage Agents | Pod restart | Stateless (state in Postgres) | documented live |

---

*Document generated: 2026-04-22*  
*Auditor: LLM*  
*Repository: `/Users/glasslab/cluster-config`*
