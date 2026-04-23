# Generic Experiment Implementation Plan

This document turns the generic experiment contract into a concrete execution
plan for Glasslab.

The most important sequencing rule is:

- do not operationalize generic experiment runs on top of ambiguous state

Before Glasslab becomes a broader experiment platform, it must be explicit
about:

- what is a record
- what is a file
- what is durable
- what is reconstructed
- what is secret
- what is transient

If those boundaries remain muddy, a generic experiment API will only spread the
confusion to more workloads.

## Executive Summary

The implementation should happen in three phases:

1. **State and storage cleanup**
2. **Generic experiment contract**
3. **First workload integration**

The first phase is the prerequisite.

## Phase 1: State And Storage Cleanup

This phase is about making the platform trustworthy before adding more
execution surface.

### Goal

Reach a clean platform boundary:

- Postgres owns records
- MinIO and/or shared storage own files
- secrets are backed up and restorable
- ephemeral versus durable paths are documented and enforced

### 1.1 Classify stateful objects

Make a definitive inventory under four categories:

- **records**
- **files**
- **secrets**
- **ephemeral caches/runtime scratch**

Target classification:

#### Records

Should live in Postgres:

- sessions
- stage records
- source metadata
- run metadata
- comparison records
- decisions
- campaign lineage
- schedule records

#### Files

Should live in MinIO and/or shared filesystem:

- source-document blobs
- `run_manifest.json`
- `config.json`
- `metrics.json`
- `status.json`
- `artifacts_index.json`
- logs
- checkpoints
- embeddings
- plots
- reports
- notebooks

#### Secrets

Should exist only in Kubernetes Secrets and encrypted `.44` backup artifacts:

- Postgres credentials
- MinIO credentials
- GHCR pull secrets
- gateway tokens
- any external API keys

#### Ephemeral

May remain non-durable:

- unpacked runtime bundles
- temporary job scratch space
- pod-local caches
- transient staging directories

### 1.2 Eliminate remaining mixed-responsibility paths

The main rule is:

- no system-of-record data on the artifacts share

Required checks:

- confirm no active workflow/session metadata is still written to JSON on NFS
- confirm source-document metadata is not split between Postgres and ad hoc sidecars
- confirm run comparison state is not hidden in files that are treated like records

### 1.3 Normalize artifact ownership

Define one artifact ownership rule:

- `workflow-api` owns references and metadata
- file/object storage owns artifact bytes

Required cleanup:

- standardize the run artifact bundle shape
- define which artifacts are mandatory versus optional
- define how artifact refs are persisted in Postgres

Authoritative references:

- `artifact-contract.md`
- `comparison-record-contract.md`

### 1.4 Finish secret durability posture

Before broadening the platform:

- verify encrypted `.44` secret backup is current and restorable
- confirm restore runbooks match the current secret set
- remove stale references to deleted services from backup/restore docs

### 1.5 Decide current file plane

For near-term operations, be explicit:

- datasets: shared filesystem or MinIO
- artifacts: MinIO or shared filesystem

Do not leave this as a vague “both maybe” story in product-facing docs.

Recommended near-term posture:

- datasets: shared RWX filesystem
- source-document blobs: shared RWX filesystem
- artifacts: MinIO for durable run bundles, shared filesystem only where needed for compatibility

Authoritative reference:

- `near-term-byte-plane-decision.md`

## Phase 2: Generic Experiment Contract

Once state ownership is clean, the generic contract can be implemented.

### Goal

Replace topic-specific run concepts with a generic experiment-run model.

### 2.1 Add generic run submission schema

In `workflow-api`, define one generic request schema for:

- `experiment_type`
- `workload_id`
- `image_ref`
- `entrypoint`
- `config_payload`
- `dataset_bindings`
- `resources`
- `budget`
- `artifact_contract`
- `metric_contract`
- lineage fields such as `parent_run_id`

This should become the substrate under existing bounded experiment flows.

### 2.2 Add generic result-ingest schema

Define one generic result payload for:

- terminal status
- metrics
- artifact refs
- runtime metadata
- optional evaluator-ready summary

This should be the standard write-back path from Jobs and runners.

### 2.3 Evolve workflow-registry into workload-definition registry

Do not throw away the current registry.
Generalize it.

Each definition should declare:

- `workload_id`
- `experiment_type`
- schema version
- allowed image policy
- entrypoint policy
- resource bounds
- required artifacts
- evaluator type
- approval tier

The current `workflow_family` concept can remain as a compatibility field, but
the registry should become workload-definition oriented.

### 2.4 Keep comparison generic

Do not add comparison endpoints per workload.

Use:

- generic run selection
- generic evaluator binding
- workload-specific metric weighting from registry/evaluator config

### 2.5 Keep command surface stable

Do not widen the operator command surface to expose platform internals.

The primary loop should stay:

- `!new`
- `!state`
- `!add`
- `!plan`
- `!check`
- `!run`
- `!compare`
- `!decide`
- `!next`

Only the backend contract should become more generic.

## Phase 3: First Workload Integration

Do exactly one real workload first.

Recommended first candidate:

- `glasslab-metric-search`

### Goal

Prove the generic contract with one concrete one-GPU workload without adding
special-case endpoints.

### 3.1 Register one workload definition

Example:

- `workload_id = metric-search-v0`
- `experiment_type = gpu-training-job`
- schema = `RunSpec v0`
- evaluator = `art_retrieval_v1`

### 3.2 Add one Kubernetes Job template

The template should accept:

- image ref
- entrypoint
- run/config payload
- dataset bindings
- resource request
- output destination

### 3.3 Add one result-ingest path

The workload should publish:

- terminal status
- metric bundle
- artifact refs

through the generic result API.

### 3.4 Add one evaluator contract

For the first workload, define:

- required metrics
- composite ranking logic
- comparison summary shape

The evaluator logic may be workload-specific internally, but the API contract
must remain generic.

## Suggested Work Breakdown

### Track A: State and storage

Owner focus:

- storage docs
- artifact ownership
- secret DR
- Postgres/file split validation

Deliverables:

- updated state map
- artifact contract doc
- secret restore validation note
- file-plane decision note

### Track B: Control-plane schemas

Owner focus:

- `workflow-api` generic experiment schema
- generic result ingest schema
- persistence model changes

Deliverables:

- schema definitions
- persistence tables/models
- API docs
- tests

### Track C: Registry evolution

Owner focus:

- registry schema changes
- workload-definition examples
- approval/policy constraints

Deliverables:

- updated registry schema
- at least one migrated example
- validation tests

### Track D: First workload bridge

Owner focus:

- `glasslab-metric-search` integration
- Job template
- evaluator/result flow

Deliverables:

- one runnable workload definition
- one working Job template
- one compare path using generic APIs

## Immediate Next Steps

In order:

1. write one authoritative artifact contract doc
2. write one authoritative stateful-object inventory doc
3. write one authoritative near-term byte-plane decision
4. write one authoritative comparison-record contract
5. audit current `workflow-api` persistence to confirm no record/file mixing remains
6. define generic experiment submission schema
7. define generic result-ingest schema
8. evolve the registry model
9. integrate `glasslab-metric-search` as the first workload

## Success Criteria

This plan is successful when:

1. records and files have clean ownership boundaries
2. no new research workload requires bespoke endpoints
3. one generic run API can schedule multiple workload definitions
4. one generic result API can ingest outputs from those workloads
5. one real workload runs end-to-end through the generic path

## Bottom Line

The right order is:

- clean up state
- genericize the experiment contract
- integrate one workload

Do not reverse that order. If state remains ambiguous, the platform will become
more general and less reliable at the same time.
