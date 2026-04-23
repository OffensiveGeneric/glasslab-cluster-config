# Storage Contract 2026-04

This document is the concrete storage boundary for Glasslab v2.

It replaces the informal pattern where Postgres, shared PVCs, JSON files, and
MinIO were treated as interchangeable fallback layers.

## Design Rule

Postgres owns records.

MinIO owns durable run artifacts and source-document blobs.

Shared filesystems own datasets and temporary execution staging.

Pod-local filesystems own scratch only.

No component should use a file/object store as the system of record for workflow
state, and no component should treat Postgres as a blob store.

## Storage Classes By Data Type

| Data type | Canonical store | Current bridge | Owner |
| --- | --- | --- | --- |
| Sessions | Postgres | none | `workflow-api` |
| Designs, decisions, campaigns | Postgres | none | `workflow-api` |
| Run records | Postgres | none | `workflow-api` |
| Comparison records | Postgres | none | `workflow-api` |
| Dataset files | shared dataset filesystem | later mirrored/indexed in MinIO if useful | operator/dataset sync |
| Source-document blobs | MinIO | filesystem until credentials and buckets are wired | `workflow-api` |
| Run artifact bundles | MinIO | shared artifacts PVC staging | workload runner + `workflow-api` |
| Reports and comparison files | MinIO | shared artifacts PVC staging | reporter/evaluator |
| Logs | MinIO for durable logs, pod logs for live debugging | shared artifacts PVC staging | runner |
| Secrets | Kubernetes Secrets plus encrypted `.44` backup | local `.44` manifests | operator |
| Cache/scratch | pod-local or node-local ephemeral storage | none | individual workload |

## Buckets

Use a small fixed bucket set.

| Bucket | Purpose |
| --- | --- |
| `glasslab-run-artifacts` | immutable per-run artifact bundles |
| `glasslab-source-documents` | fetched PDFs, HTML snapshots, and source blobs |
| `glasslab-comparisons` | comparison reports, summaries, and evaluator outputs |

Do not put workflow/session state in these buckets.

## Object Key Layout

Run artifacts:

```text
s3://glasslab-run-artifacts/runs/{run_id}/run_manifest.json
s3://glasslab-run-artifacts/runs/{run_id}/config.json
s3://glasslab-run-artifacts/runs/{run_id}/metrics.json
s3://glasslab-run-artifacts/runs/{run_id}/artifacts_index.json
s3://glasslab-run-artifacts/runs/{run_id}/report.md
s3://glasslab-run-artifacts/runs/{run_id}/status.json
s3://glasslab-run-artifacts/runs/{run_id}/logs/runner.log
```

Source documents:

```text
s3://glasslab-source-documents/sources/{document_id}/source.pdf
s3://glasslab-source-documents/sources/{document_id}/metadata.json
```

Comparisons:

```text
s3://glasslab-comparisons/comparisons/{comparison_id}/comparison.json
s3://glasslab-comparisons/comparisons/{comparison_id}/summary.md
```

## Record References

Postgres records should store object references, not object bytes.

Examples:

```json
{
  "run_id": "abc123",
  "artifact_refs": {
    "metrics": "s3://glasslab-run-artifacts/runs/abc123/metrics.json",
    "report": "s3://glasslab-run-artifacts/runs/abc123/report.md",
    "logs": "s3://glasslab-run-artifacts/runs/abc123/logs/"
  }
}
```

```json
{
  "comparison_id": "cmp123",
  "artifact_refs": {
    "comparison": "s3://glasslab-comparisons/comparisons/cmp123/comparison.json",
    "summary": "s3://glasslab-comparisons/comparisons/cmp123/summary.md"
  }
}
```

## Near-Term Execution Model

For Kubernetes Jobs, keep the shared artifacts PVC as the staging plane.

The runner writes to:

```text
/mnt/artifacts/{run_id}/
```

Then a backend-owned promotion step copies the completed bundle into MinIO and
records the resulting `s3://` refs in Postgres.

That keeps workload containers simple while making MinIO the canonical durable
artifact plane.

The promotion step should be idempotent:

- if the object already exists with the same content, keep it
- if a required file is missing, fail promotion explicitly
- if upload succeeds but Postgres update fails, retry using the same keys

## Explicit Non-Goals

Do not:

- set `GLASSLAB_WORKFLOW_API_STORE_JSON_PATH` to an `s3://` URI
- use MinIO as the workflow/session metadata store
- teach every service to pretend S3 is a local filesystem
- instantiate clients with hidden default `Settings()` inside storage helpers
- commit root object-store credentials into code or ConfigMaps
- require every workload container to know MinIO credentials in v0

## Implementation Phases

### Phase 0: Current Safe State

- Postgres is the workflow/session/run record store.
- Shared artifacts PVC is the run-artifact staging plane.
- Source documents default to filesystem mode unless MinIO credentials are wired.
- MinIO exists as a durable object store but is not yet the canonical artifact
  plane for all new runs.

### Phase 1: Source Documents To MinIO

Wire `workflow-api` with MinIO credentials from the existing MinIO Secret.

Set:

```text
GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_STORAGE_MODE=minio
GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_BUCKET=glasslab-source-documents
GLASSLAB_WORKFLOW_API_MINIO_ENDPOINT=glasslab-minio.glasslab-v2.svc.cluster.local:9000
```

Add env wiring for:

```text
GLASSLAB_WORKFLOW_API_MINIO_ACCESS_KEY
GLASSLAB_WORKFLOW_API_MINIO_SECRET_KEY
```

Validate source intake before changing run artifacts.

### Phase 2: Artifact Promotion

Add a `workflow-api` artifact promotion helper:

```text
POST /experiments/runs/{run_id}/artifacts/promote
```

The helper reads `/mnt/artifacts/{run_id}/`, uploads required artifacts to
`glasslab-run-artifacts`, and updates the run record's `artifact_refs`.

This is preferred over teaching `run_artifacts.py` to read every possible URI.

### Phase 3: Comparison Promotion

Have evaluator/reporter output comparison files to staging, then promote them to:

```text
s3://glasslab-comparisons/comparisons/{comparison_id}/
```

The `ComparisonRecord` in Postgres stores the refs.

### Phase 4: Optional Direct Writes

Only after promotion is reliable, allow workload containers to write directly to
MinIO using narrowly scoped credentials.

This is optional. The platform should work with staging plus promotion first.

## Migration Rules

- Existing `/mnt/artifacts/{run_id}` bundles remain valid.
- New records should prefer `s3://` refs after promotion.
- Reads should prefer Postgres refs first, then fall back to the staging path for
  older runs.
- JSON workflow state remains backup/import material only.

## Health Checks

Minimum checks before declaring MinIO-backed artifacts ready:

```bash
kubectl -n glasslab-v2 rollout status deploy/glasslab-minio --timeout=120s
kubectl -n glasslab-v2 get secret glasslab-v2-minio
kubectl -n glasslab-v2 exec deploy/glasslab-workflow-api -- sh -lc 'test -d /mnt/artifacts'
```

After promotion exists:

```bash
curl -fsS -X POST http://127.0.0.1:18081/experiments/runs/{run_id}/artifacts/promote
curl -fsS http://127.0.0.1:18081/runs/{run_id}
```

The returned run should contain `s3://glasslab-run-artifacts/...` artifact refs.

## Bottom Line

The storage stack should be boring:

- Postgres for records
- MinIO for durable blobs
- shared filesystems for datasets and staging
- ephemeral storage for scratch

Anything else is compatibility or migration glue, not architecture.
