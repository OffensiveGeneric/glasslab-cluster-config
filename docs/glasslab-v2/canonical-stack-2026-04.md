# Canonical Stack 2026-04

This document is the current source of truth for what Glasslab is.

It is intentionally narrower than older research-assistant and literature-first notes.

## Product shape

Glasslab is a runner-first research system.

Its job is to:

* keep a bounded research session
* turn the current session into a reviewable experiment plan
* launch approved runs
* compare results
* record decisions
* propose the next bounded mutation

It is not primarily:

* a literature-search product
* a general chat agent
* an autonomous scientist
* an OpenClaw-centered orchestration system

## Canonical control path

The canonical command path is:

* `whatsapp-gateway`
* `research-ingress`
* `research-command-router`
* `workflow-api`

This path owns the primary command loop.

The primary loop is:

* `!new`
* `!state`
* `!add`
* `!plan`
* `!check`
* `!run`
* `!compare`
* `!decide`
* `!next`

Legacy aliases may continue to exist, but they are not the product center.

## Canonical backend control plane

The canonical control plane is:

* `workflow-api`

`workflow-api` owns:

* session records
* source intake records
* design drafts
* run creation
* autoresearch campaign transitions
* evaluator/report handoff

## Canonical data ownership

### Metadata and records

Target system of record:

* `Postgres`
* `Postgres` with pgvector for semantic/vector indexes

This includes:

* sessions
* stage records
* source metadata
* designs
* runs
* decisions
* campaign state
* embeddings, vector index metadata, and pointers to source/artifact files

### Files and objects

Target file/object plane:

* `.207` g-nas shared filesystem through the `glasslab-shared-datasets` and
  `glasslab-shared-artifacts` PVCs
* MinIO only where object-style access is deliberately needed

This includes:

* source documents
* artifacts
* logs
* reports
* notebooks

## Canonical infrastructure posture

### Cluster services

Keep private by default:

* `workflow-api`
* `Postgres`
* `NATS`
* `MinIO API`

Use `ClusterIP` by default.

### Human-facing surfaces

Keep exactly one primary command surface.

Current primary command surface:

* repo-owned WhatsApp/control shell through `whatsapp-gateway`

There is no supported secondary conversational surface in the current product.

## Canonical deployment posture

### Image path

Normal path:

* private GHCR pull

Break-glass only:

* local image import

### Admin/apply host

For now, `.44` remains:

* canonical apply host
* validation host
* local secret source of truth

That is an operational constraint, not a product identity.

## Canonical product language

Use this language in current-state docs:

* session
* source intake
* plan
* preflight
* run
* compare
* decide
* next bounded variant

Avoid centering current docs on:

* literature pipeline
* general research assistant
* multi-agent orchestration

## Primary success condition

A user should be able to:

1. create or resume a session
2. add a little evidence or context
3. generate a bounded current plan
4. check readiness
5. launch a run
6. compare the result
7. record a decision
8. launch the next bounded mutation

without depending on broad literature search or any conversational fallback layer.
