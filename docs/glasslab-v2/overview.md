# Glasslab v2 Overview

Glasslab v2 keeps the existing cluster and v1 stack intact while introducing a clearer backend for approved, repeatable experiment workflows.

## Roles

- `services/workflow-api`: the orchestration backend. It accepts structured run requests, validates them against the approved registry, writes a canonical run manifest, and hands work to bounded executors.
- `services/workflow-registry`: the explicit catalog of allowed workflow families. This is where supported inputs, models, runner images, resource profiles, artifact expectations, and approval tiers are declared.
- `services/evaluator`: deterministic comparison logic for multiple runs once artifact bundles exist.
- `services/reporter`: deterministic report synthesis from manifests, metrics, and evaluator output.
- `services/openclaw-config`: tracked OpenClaw agents, prompts, bindings, and policy. OpenClaw is the operator shell and gateway, not the workflow brain.

## Core flow

`request -> workflow family lookup -> registry-backed validation -> canonical run_manifest -> Kubernetes Job submission -> artifacts -> evaluation -> report`

## Supporting platform services

- `Postgres`: durable run state, workflow metadata, and queue history once v2 moves beyond in-memory storage.
- `MinIO`: object storage for artifact bundles, reports, and optional dataset snapshots.
- `NATS`: internal event bus for status updates, notifications, and decoupled background processing.
- `Kubernetes Jobs`: bounded executors for workflow runs. Jobs should stay narrow, explicit, and tied to approved runner images.

## Design rule

Do not make v2 clever before making it legible. Schemas, workflow definitions, artifact contracts, and approval tiers should stay explicit and reviewable in Git.
