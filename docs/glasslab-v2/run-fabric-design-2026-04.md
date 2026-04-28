# Glasslab Run Fabric Design 2026-04

Status: proposed infrastructure design

Date: 2026-04-28

## Purpose

This document narrows the infrastructure product.

The immediate product is **Glasslab Run Fabric**: a small lab compute system that
can submit bounded workloads, run them on the lab cluster, persist state and
artifacts, compare results, and optionally call local model-serving endpoints.

This document intentionally sets aside literature search, experimental-design
generation, and autonomous research behavior. Those can be discussed as product
layers later. They should not define the core infrastructure contract.

## Problem

Glasslab started as a way to learn and exercise Kubernetes in the lab. It then
grew into a broader research-assistant system before the infrastructure product
was made explicit.

The result is useful but over-coupled:

- `workflow-api` is simultaneously a run API, session API, literature pipeline,
  design-draft store, scheduling surface, source-document store, and
  autoresearch engine.
- The command path has several layers before it reaches run creation.
- Multiple storage systems are present, with older docs treating Postgres,
  shared filesystems, JSON files, and MinIO as partially interchangeable.
- The two-Mac model-serving stack is useful but can easily become a second
  cluster project if it is coupled to Kubernetes lifecycle.
- `metric-search-v0` is the right first GPU workload, but it currently exposes
  contract gaps between the workload repo and the cluster repo.

The infrastructure needs a smaller center.

## Product Definition

The run fabric exists to answer one operator question:

> Can I run this bounded workload on lab compute and trust the resulting record?

The core workflow is:

1. Select a workload.
2. Provide config, dataset bindings, budget, and image.
3. Run preflight checks.
4. Submit a Kubernetes Job.
5. Track status and logs.
6. Persist run metadata in Postgres.
7. Persist large artifacts on `.207`.
8. Ingest terminal metrics and artifact references.
9. Compare runs.
10. Clone or mutate a run.

Everything else should be an adapter or feature layer.

## Non-Goals

This design does not try to solve:

- literature search
- experiment design
- autonomous scientist behavior
- chat UX
- public multi-tenant access
- Kubernetes membership for the Macs
- a general MLOps platform
- a new vector database service
- direct object-store writes from every workload container

## Design Principles

- One control plane for runs: `workflow-api`.
- One record store: Postgres.
- One large-byte plane: `.207` g-nas through Kubernetes PVCs.
- One scheduling primitive for bounded experiments: Kubernetes Jobs.
- One stable inference boundary for the Macs: HTTP, preferably
  OpenAI-compatible `/v1`.
- Job runners write terminal bundles. The cluster ingests and indexes them.
- MinIO, NATS, WhatsApp, and stage agents are optional until they carry a
  measured core responsibility.
- Compatibility routes may remain, but operator automation should target stable
  explicit IDs instead of global `latest` state.

## Target Architecture

```text
operator CLI/dashboard
        |
        v
workflow-api ---------------> Postgres + pgvector
   |                                |
   | creates Jobs                   | run records, metrics summaries,
   v                                | artifact refs, comparisons,
Kubernetes Job                      | vector index metadata
   |
   | mounts
   v
.207 g-nas PVCs
   |-- /mnt/datasets/{dataset}
   |-- /mnt/artifacts/{run_id}

optional adapters:
WhatsApp -> research-ingress -> command-router -> workflow-api

optional model help:
workflow-api or tools -> exo/OpenAI-compatible endpoint on Macs
```

## Core Components

### `workflow-api`

Keep `workflow-api` as the run control plane.

Core responsibilities:

- validate workload definitions
- create run records
- generate run manifests
- submit Kubernetes Jobs
- expose run status, logs, artifacts, and comparisons
- ingest terminal run bundles
- maintain vector metadata for searchable records and artifact text

Defer or isolate:

- literature flow
- design-draft generation
- source-harvesting pipelines
- autoresearch transitions
- broad session memory

Those can remain in the repo, but the run fabric should be testable with only
run endpoints.

### Kubernetes

Use Kubernetes for:

- long-running or GPU-backed experiment Jobs
- internal services
- PVC-mounted shared datasets and artifacts
- resource requests, priority, labels, and TTL cleanup

Do not use Kubernetes for:

- Mac lifecycle
- conversational state
- every small helper script
- storage semantics that should belong to Postgres or `.207`

The current `KubernetesJobSubmitter` direction is right: one accepted run maps
to one Job, with labels, run metadata env vars, resource requests, dataset PVC,
and artifact PVC.

### Postgres And pgvector

Postgres is the system of record for metadata and decisions.

Near-term acceptable state:

- `workflow_state` JSONB as compatibility and migration storage
- `vector_index_items` for initial vector metadata

Target state:

- normalized `runs`
- normalized `run_events`
- normalized `artifacts`
- normalized `comparisons`
- normalized `datasets`
- `vector_index_items` for embeddings and pointers

Postgres should store summaries and references, not large files.

### `.207` g-nas

The `.207` g-nas export is the canonical large-byte plane for the current phase.

Use:

- `glasslab-shared-datasets` mounted read-only into Jobs where possible
- `glasslab-shared-artifacts` mounted writable for per-run output bundles

Canonical run output:

```text
/mnt/artifacts/{run_id}/
  run_manifest.json
  config.json
  metrics.json
  artifacts_index.json
  report.md
  status.json
  logs/runner.log
```

Large optional artifacts such as checkpoints, embeddings, plots, and notebooks
belong under the same run directory.

### MinIO

MinIO should not be required for GPU run completion in the current phase.

Keep it as optional object-style infrastructure for:

- source-document mirroring
- artifact promotion
- external S3-style access
- future lifecycle policies

Do not require every workload container to know MinIO credentials in v0.

### NATS

NATS should not be part of the required run-fabric smoke path until it carries a
real async workload.

If eventing becomes important, decide explicitly whether it is:

- ephemeral notification bus
- durable work queue
- audit/event stream

Until then, Postgres plus Kubernetes Job status is enough for the core loop.

### Two-Mac Model Serving

The Macs should remain separate service hosts.

Use them for:

- exo distributed inference
- OpenAI-compatible model-serving endpoints
- optional ranker or reranker services

Do not make them Kubernetes workers in the current phase.

The cluster should depend only on:

- base URL
- model name
- API key if needed
- health check
- timeout

The known-good exo/RDMA workflow remains operational documentation, not a
Kubernetes cluster requirement.

## Primary API Shape

The run fabric should have a narrow stable API:

- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/logs`
- `GET /runs/{run_id}/artifacts`
- `POST /runs/{run_id}/artifacts/ingest`
- `POST /experiments/runs`
- `POST /experiments/compare`
- `GET /workflow-families`
- `GET /workflow-families/{workflow_id}/execution-preflight`

Session and command-router routes may call these APIs. They should not be the
only supported path for operating runs.

## Run Bundle Contract

A runner must produce a terminal bundle whether the experiment succeeds or
fails.

Minimum success bundle:

- `run_manifest.json`
- `config.json`
- `metrics.json`
- `artifacts_index.json`
- `report.md`
- `status.json` with `status: succeeded`
- `logs/runner.log`

Minimum failure bundle:

- `run_manifest.json`
- `config.json`
- `artifacts_index.json`
- `status.json` with `status: failed`
- `logs/runner.log`
- optional `error.json`
- optional `report.md`

The Job exit code should match the terminal state. Failed experiments should not
pretend to be successful just to write partial artifacts.

## Ingestion Model

The cluster should not require workload containers to call back into
`workflow-api`.

Preferred v0:

1. Job writes to `/mnt/artifacts/{run_id}`.
2. Job exits.
3. `workflow-api` or a small reconciler observes Job terminal state.
4. Ingestion validates the run bundle.
5. Ingestion stores terminal status, metrics summary, and artifact references in
   Postgres.

This keeps runner credentials narrow and makes failed runs debuggable from the
shared artifact plane.

## Operator Surface

The primary operator surface should be a small CLI or dashboard that talks
directly to `workflow-api`.

Required operator actions:

- list workloads
- preflight workload
- submit run
- watch run
- tail logs
- list artifacts
- ingest or reingest artifacts
- compare runs
- clone run spec

WhatsApp and command-router can remain useful adapters. They should not be the
only way to debug the system.

## Golden Workload

`metric-search-v0` should be the proving workload for the run fabric.

A release is not healthy until a tiny metric-search GPU run can:

- pass preflight
- schedule on the GPU node
- mount datasets and artifacts
- write a complete terminal bundle under `.207`
- have artifacts ingested into Postgres
- expose metrics through `GET /runs/{run_id}`
- participate in comparison

## Migration Plan

### Phase 0: Document And Freeze The Core

- Adopt this document as the infrastructure product target.
- Treat literature/autoresearch routes as feature layers.
- Keep current manifests private by default.
- Keep Postgres and `.207` as the canonical state and byte planes.

### Phase 1: Make Metric-Search A Contract Test

- Fix metric-search terminal bundle behavior.
- Fix metric key naming.
- Add a run-bundle validator.
- Build and push a new metric-search image.
- Update `metric-search-v0` registry image after the image passes smoke.

### Phase 2: Add Artifact Ingest

- Add `POST /runs/{run_id}/artifacts/ingest`.
- Validate required artifacts before updating Postgres.
- Store metrics summaries and artifact references in normalized records or an
  explicit compatibility field.
- Add idempotent reingest.

### Phase 3: Add Operator CLI Or Dashboard

- Implement direct run operations against `workflow-api`.
- Keep command-router and WhatsApp as adapters.
- Stop relying on chat to debug run state.

### Phase 4: Normalize Postgres State

- Break the single `workflow_state` payload into tables for hot run objects.
- Keep JSONB backup/import compatibility until migration is boring.
- Add `pg_dump` backup automation to `.207`.

### Phase 5: Decide Optional Services

- Keep or remove NATS based on real queue use.
- Promote MinIO only if object-style artifact access becomes necessary.
- Put Mac inference behind one stable endpoint and health check.

## Acceptance Criteria

The run fabric is healthy when:

- `workflow-api /healthz` reports Postgres backend.
- PVC preflight confirms datasets and artifacts mounts.
- A tiny CPU run and a tiny GPU run both complete.
- Failed runner execution creates a failed terminal bundle.
- Artifact ingest survives `workflow-api` restart.
- Run comparison works from Postgres records without reading arbitrary local
  state.
- `.207` contains the large run bytes.
- Postgres contains summaries and references only.
- The Macs can be down without breaking core run submission.

## Decisions

- Keep Kubernetes.
- Keep Postgres with pgvector.
- Keep `.207` g-nas as the canonical large-artifact plane.
- Keep the Macs outside Kubernetes.
- Demote MinIO and NATS from the core path until needed.
- Treat `metric-search-v0` as the golden GPU workload.
- Discuss literature and design-generation after the run fabric is reliable.
