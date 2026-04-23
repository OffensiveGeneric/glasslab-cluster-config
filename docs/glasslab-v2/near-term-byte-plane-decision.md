# Near-Term Byte Plane Decision

This document makes the near-term file/object-plane decision explicit for
Glasslab v2.

It is a forward-looking implementation decision, not just a description of the
current mixed state.

## Decision

For the next implementation phase, Glasslab should use:

- **shared RWX filesystem for datasets**
- **shared RWX filesystem for source-document blobs**
- **MinIO as the canonical durable artifact plane for run bundles**

The intent is to stop treating “filesystem and/or MinIO” as an equally weighted
default story.

## Why These Choices

### Datasets -> shared RWX filesystem

Use the shared datasets plane for datasets because:

- datasets are often large and reused across runs
- the cluster already has a tracked RWX path for them
- jobs benefit from a stable read-only mount contract
- this avoids repeatedly materializing datasets through object-store fetch logic

Near-term rule:

- workloads should read datasets from `/mnt/datasets`
- dataset metadata and bindings still belong in Postgres records

### Source-document blobs -> shared RWX filesystem

Use the shared artifacts/filesystem path for source-document blobs for now
because:

- current `workflow-api` default already uses filesystem-backed source documents
- source-document fetch and extraction logic already assumes simple file writes
- this avoids mixing “migrate the document blob path” with “generic experiment
  contract” in the same change set

Near-term rule:

- source-document metadata belongs in Postgres
- source-document bytes live on the filesystem-backed source-document path

This is a pragmatic near-term choice, not a claim that source docs must stay on
filesystem forever.

### Run artifact bundles -> MinIO

Use MinIO as the canonical durable artifact plane for new run bundles because:

- artifacts are naturally object-like
- MinIO gives clearer URI semantics than ad hoc shared-path conventions
- it decouples artifact durability from the layout of a shared NFS tree
- it is a cleaner fit for generic experiment workloads and result ingestion

Near-term rule:

- new or migrated run-result flows should treat object-store URIs as canonical
- shared-filesystem artifact paths remain compatibility paths until older flows
  are migrated

## Canonical Paths

### Datasets

Canonical mount path:

- `/mnt/datasets`

Canonical backing plane:

- shared RWX filesystem

### Source documents

Canonical path for bytes:

- `/mnt/artifacts/source-documents`

Canonical backing plane:

- shared RWX filesystem

### Run artifacts

Canonical reference form:

- object-store URI such as `s3://...`

Canonical backing plane:

- MinIO

Compatibility path:

- shared artifacts filesystem until the old flows are migrated

## Practical Consequences

### For `workflow-api`

- keep source-document metadata in Postgres
- keep artifact refs in Postgres
- stop treating shared-filesystem artifact paths as the long-term canonical run
  bundle location

### For workload runners

- read datasets from the shared datasets mount
- write temporary outputs locally if needed
- publish durable artifacts to MinIO as the canonical final destination

### For evaluator and reporter

- consume canonical artifact refs from Postgres
- prefer MinIO/object-store URIs for new work

## Migration Boundary

This decision does not require an instant rewrite of every existing path.

It does require this rule:

- any new generic experiment workflow should target MinIO for durable run
  artifacts from the start

The shared artifacts filesystem remains acceptable only as:

- a compatibility plane
- a staging plane
- a legacy path for older workflows

## What This Avoids

This decision avoids three recurring forms of confusion:

1. datasets treated like object-store outputs
2. source-document metadata and source-document bytes collapsing into one store
3. run artifacts drifting between shared paths and object URIs with no clear
   canonical reference

## Bottom Line

Near-term canonical byte-plane choices are:

- datasets: shared RWX filesystem
- source-document blobs: shared RWX filesystem
- run artifacts: MinIO
