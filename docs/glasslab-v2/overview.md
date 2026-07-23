# Glasslab v2 Overview

Glasslab v2 is the backend-owned research workflow layer for the lab.

It exists to turn session state into bounded, reviewable, repeatable
experiments.

## Mental Model

Read the product as:

- investigation-first
- plan-oriented
- deterministic at the control boundary
- bounded at execution time

That means:

- investigations hold the question, hypotheses, approvals, runs, and claims
- underlying sessions hold working operator and intake state
- source intake enriches the session
- a current plan is derived from the session
- preflight decides whether that plan is runnable
- explicit approval freezes the runnable plan before launch
- runs are launched through approved workflow families
- claims cite exact ingested run artifacts
- comparison and decision drive the next mutation

## Primary Product Loop

The intended loop is:

`investigation -> intake -> plan -> preflight -> approve -> run -> evidence -> claim -> next`

Compatibility aliases and older debug flows still exist, but they are not the
product center.

The first current implementation of this aggregate is documented in
[investigation-api-v0.md](investigation-api-v0.md).

## Command Surface

The canonical command path is:

- `whatsapp-gateway`
- `research-ingress`
- `research-command-router`
- `workflow-api`

Primary commands:

- `!new`
- `!state`
- `!add`
- `!plan`
- `!check`
- `!run`
- `!compare`
- `!decide`
- `!next`

Legacy aliases may remain:

- `!start`
- `!status`

OpenClaw is not part of the primary command loop.

## Service Roles

### `workflow-api`

The control plane.

Owns:

- investigations and plan-approval snapshots
- sessions
- source intake records
- design drafts
- run creation
- evidence-backed claims
- autoresearch transitions
- execution preflight
- evaluator/report handoff

### `workflow-registry`

The approved workflow catalog.

Owns:

- execution templates
- allowed inputs
- resource profiles
- runner image references
- expected artifacts
- approval tiers

### `research-ingress`

Inbound control normalization.

Owns:

- command vs non-command turn split
- deterministic forwarding to the router

### `research-command-router`

Deterministic command dispatch.

Owns:

- command matching
- argument parsing
- pinned-session routing
- one backend-owned action per primary command

### `whatsapp-gateway`

Repo-owned operator shell.

Owns:

- sender transcript persistence
- sender/session pinning
- attachment normalization
- duplicate suppression

### `evaluator` and `reporter`

Deterministic post-run services.

They should stay artifact-grounded and backend-owned.

### Stage agents

Current bounded stage-agent roles:

- `intake-agent`
- `interpretation-agent`
- `assessment-agent`
- `design-agent`

These exist to improve bounded steps inside the product loop.
They are not the primary product surface.

### OpenClaw

Optional and secondary.

If retained, it is for:

- optional chat
- summaries
- read-only or bounded help

It is not the workflow brain.
It is not the command router.

## Data Ownership

### Records

Target system of record:

- `Postgres`

This should own:

- sessions
- stage records
- source metadata
- designs
- runs
- decisions
- campaign state

### Files

Target file/object plane:

- shared filesystem and/or MinIO

This should own:

- source documents
- artifacts
- logs
- reports
- notebooks

Current technical debt:

- session/workflow state still has JSON-backed paths in `workflow-api`
- that is a migration target, not the desired steady state

## Infrastructure Posture

Keep backend services private by default:

- `workflow-api`
- `Postgres`
- `NATS`
- `MinIO API`

Use `ClusterIP` by default.

Use one primary human-facing command surface only.

Current primary human-facing surface:

- repo-owned WhatsApp/control path

## Design Rules

1. Keep command turns deterministic.
2. Keep backend ownership explicit.
3. Keep stage-agent behavior bounded.
4. Keep files and records separated conceptually and operationally.
5. Do not let historical experiments dictate current product language.

## Non-Goals

Glasslab v2 is not primarily:

- a literature-search product
- a general chat shell
- an autonomous multi-agent scientist
- an OpenClaw-centered orchestration stack

It is a bounded research workflow system with a narrow operator loop.
