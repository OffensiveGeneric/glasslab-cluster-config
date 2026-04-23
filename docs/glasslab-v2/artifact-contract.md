# Artifact Contract

This document is the authoritative artifact contract for Glasslab v2.

It defines:

- what counts as a run artifact
- which artifacts are required
- which artifacts are optional
- which service owns the bytes
- which service owns the references and metadata

The central rule is:

- `workflow-api` owns run and artifact metadata
- file/object storage owns artifact bytes

Artifacts are files or object-store objects.
They are not the system of record for workflow state.

## Scope

This contract applies to bounded Glasslab experiment runs, regardless of
workload type.

Examples:

- tabular runs
- GPU training runs
- metric-search runs
- evaluation-only runs

## Ownership Model

### Record owner

`workflow-api` must persist:

- run identity
- workload identity
- session/campaign association
- terminal run status
- artifact references
- comparison associations
- evaluator summary references

This metadata belongs in Postgres.

### Byte owner

Artifact bytes belong in the file/object plane:

- MinIO
- shared artifacts filesystem

Near-term current posture:

- shared artifacts filesystem is still an active contract path
- MinIO is the intended durable artifact direction

## Required Run Artifacts

Every completed or terminal run must produce these artifacts.

### `run_manifest.json`

Purpose:

- immutable description of what Glasslab intended to run

Minimum contents:

- run id
- workload id or workflow id
- image ref
- entrypoint / command
- resource request
- budget
- dataset bindings
- config reference or embedded config summary
- creation timestamp

Owner:

- produced at submission time by the control plane or runner wrapper

### `config.json`

Purpose:

- exact resolved experiment configuration used by the run

Minimum contents:

- model/backbone settings
- dataset split identifiers
- objective/loss settings
- trainer/evaluator settings
- workload-specific config values

Owner:

- runner/workload image

### `status.json`

Purpose:

- terminal execution status summary

Minimum contents:

- run id
- terminal state
- started_at
- finished_at
- node / executor metadata when available
- failure summary if failed

Owner:

- runner/workload image or generic result-ingest writer

### `metrics.json`

Purpose:

- structured primary metrics emitted by the run

Minimum contents:

- run id
- workload-specific metrics
- metric timestamps or completion metadata if useful

Owner:

- runner/workload image

### `artifacts_index.json`

Purpose:

- machine-readable listing of artifact names and URIs for the run bundle

Minimum contents:

- artifact logical name
- URI/path
- content type when known
- size/hash when known

Owner:

- runner/workload image or artifact finalizer

### `report.md`

Purpose:

- deterministic human-readable summary of the run

Minimum contents:

- what ran
- key metrics
- notable warnings or failures
- links/refs to richer artifacts

Owner:

- reporter or workload-specific report step

### `logs/`

Purpose:

- raw execution logs retained for operator debugging

Minimum contents:

- stdout/stderr or equivalent execution logs

Owner:

- executor / runner wrapper

## Optional Artifacts

These are allowed but not mandatory across all workloads.

### `comparison.json`

Produced by:

- evaluator

Use:

- multi-run comparison output

### `summary.md`

Produced by:

- evaluator or reporter

Use:

- deterministic comparison summary

### `analysis_notebook.ipynb`

Produced by:

- reporter or workload-specific analysis step

Use:

- richer interactive review

### `checkpoint.*`

Produced by:

- training workloads

Use:

- resumable model state

### `embeddings.*`

Produced by:

- retrieval / metric-learning workloads

Use:

- embedding export for offline analysis

### `plots/`

Produced by:

- workload or reporter

Use:

- metric curves, confusion plots, retrieval panels, robustness plots

### `predictions.*`

Produced by:

- inference/evaluation workloads

Use:

- row-level or item-level outputs

## Naming Rules

Use these names as the canonical logical names:

- `run_manifest.json`
- `config.json`
- `status.json`
- `metrics.json`
- `artifacts_index.json`
- `report.md`
- `logs/`

Do not introduce alternate names for the same concept unless the workload has a
genuinely distinct artifact class.

Examples of names to avoid for the primary metric file:

- `results.json`
- `scores.json`
- `metrics_summary.json`

Pick one:

- `metrics.json`

## URI Rules

Every persisted artifact reference should be expressible as:

- object-store URI
- filesystem-backed path/URI

Examples:

- `s3://glasslab-artifacts/run-123/metrics.json`
- `/mnt/artifacts/run-123/metrics.json`

The run metadata layer should store references, not duplicate artifact bytes.

## Metadata Versus Files

The following belong in records, not only in files:

- run terminal status
- key metric summary
- artifact references
- evaluator summary references

The following belong in files:

- logs
- reports
- notebooks
- checkpoints
- raw metric exports
- raw prediction dumps

## Workload Extensions

Workload definitions may declare optional extra artifacts, but they must not
rename the required core set.

Example:

- `metric-search-v0` may add:
  - `embeddings.parquet`
  - `retrieval_examples.json`
  - `plots/retrieval_panels/`

## Near-Term Storage Posture

Current practical posture:

- records: Postgres
- datasets: shared filesystem
- artifact bytes: shared filesystem now, MinIO preferred over time

This document does not force an immediate migration of all artifact bytes into
MinIO, but it does make the ownership boundary explicit.

## Success Criteria

This contract is being followed when:

1. every run yields the required core artifact set
2. artifact references are persisted in Postgres
3. no workflow/session state is hidden only inside artifact files
4. workload-specific extras do not fork the core naming scheme
