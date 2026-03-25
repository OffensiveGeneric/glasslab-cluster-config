# External Researcher: What We Can Offer Now

This note answers a practical question:

What can Glasslab safely offer to an outside researcher **right now**, based on the latest documented in-lab state?

## Short Answer

Glasslab can likely offer:

- bounded CPU-oriented Kubernetes jobs
- reviewed, admin-mediated workflow runs
- artifact-oriented experiment execution through the existing v2 backend path

Glasslab should **not** yet offer:

- broad self-service cluster access
- casual GPU tenancy
- unrestricted arbitrary workloads
- direct unsupervised access to internal services

## Current Practical Capacity

Based on the 2026-03-24 documented state:

- worker nodes:
  - `node01`
  - `node02`
  - `node03`
  - `node04`
  - `node05`
- documented GPU workers:
  - `node01`
  - `node02`
  - `node04`
- most obvious near-term CPU landing zone:
  - `node03`

Important caveats:

- `node01` is already carrying several core v2 services
- `node02` still has the legacy `vllm` pod reserving its GPU
- `node05` is hosting NATS and has recently been used for completed Jobs

That means the cluster has usable capacity, but not a clean multi-tenant empty pool.

## Safest Offer Right Now

The safest outside-researcher offer today is:

- admin-reviewed runs only
- bounded workflow families only
- CPU-first where possible
- artifacts delivered through the existing Glasslab v2 path

In practical terms:

- researcher proposes or supplies a bounded experiment
- lab admins map it to an approved workflow or reviewed custom path
- `workflow-api` submits the job
- the researcher receives resulting artifacts and summary output

This is much safer than giving direct access to raw cluster resources.

## What Is Probably Fine To Offer

- approved tabular or similar bounded benchmark jobs
- reviewed paper-to-experiment reproductions inside explicit workflow constraints
- artifact delivery:
  - CSV
  - logs
  - result summaries
  - optional notebook or report artifacts

## What Is Not Ready To Offer

- direct namespace self-service for outside users
- arbitrary container submission without review
- unrestricted GPU scheduling
- direct credentials for internal services such as Postgres, MinIO, or OpenClaw
- a claim that the cluster is already hardened for external multi-user research tenancy

## Best Current Operating Model

For now, treat outside-researcher use as:

- supervised
- reviewed
- bounded
- backend-mediated

That still allows useful collaboration without pretending the lab is already a polished multi-tenant research platform.

## References

- `../machine-state-2026-03-24.md`
- `../live-state-2026-03-24.md`
- `security-model.md`
