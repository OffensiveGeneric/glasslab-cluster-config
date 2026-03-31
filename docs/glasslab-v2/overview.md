# Glasslab v2 Overview

Glasslab v2 keeps the existing cluster and v1 stack intact while introducing a clearer backend for approved, repeatable experiment workflows.

## Mental Model

The product should read as session-first:

- sessions hold the durable research state and are the main object operators work in
- skills are bounded capabilities that update that session state in controlled steps
- workflow families are execution templates selected only when the work is ready to run
- the first operator step should recover the latest session or create one from the latest staged research problem before jumping to execution templates
- execution templates should be coarse lab job shapes such as CPU tabular, literature-backed CPU experiments, GPU experiments, or replication runs, not research-topic labels

Current product priority:

- make the session -> literature -> interpretation -> design -> bounded experiment loop usable first
- add a bounded autoresearch lane for methodology drafts, approved validation runs, explicit scoring, and reviewable keep/discard decisions
- treat the stage agents as backend quality improvements to that loop, not as the main near-term product milestone
- keep the long-term target aligned with iterative research systems like `autoresearch`: persistent context, bounded experiments, result comparison, and explicit next-step proposals

Current narrowing:

- prioritize the experiment-runner side over broad literature cleverness
- keep manual paper/source add sufficient for now if that makes interpretation -> design -> run more dependable
- make interpretation outputs more bounded and directly actionable by approved workflow templates
- treat broad technique knowledge as input to methodology drafting and autoresearch, not as permission for unconstrained execution

## Operator Bootstrap

If the operator is missing required state, keep the response narrow:

- name the missing prerequisite
- give one concrete next step
- do not chain unrelated recovery actions in the same turn
- prefer session-scoped reads and writes over global `latest` answers once a session exists

## Roles

- `services/workflow-api`: the orchestration backend. It accepts structured session- and run-related requests, validates execution against the approved registry, writes a canonical run manifest, and hands work to bounded executors.
- `services/workflow-registry`: the explicit catalog of allowed execution templates. This is where supported inputs, models, runner images, resource profiles, artifact expectations, and approval tiers are declared.
- `services/evaluator`: deterministic comparison logic for multiple runs once artifact bundles exist.
- `services/reporter`: deterministic report synthesis from manifests, metrics, and evaluator output.
- `services/openclaw-config`: tracked OpenClaw agents, prompts, bindings, and policy. OpenClaw is the operator shell and gateway, not the workflow brain.

## Core flow

Near-term usable loop:

`idea -> research session -> literature harvest -> paper intake -> interpretation -> assessment -> design -> bounded experiment -> artifacts -> evaluation -> next-step decision`

Execution-template view:

`request -> workflow family lookup -> registry-backed validation -> canonical run_manifest -> Kubernetes Job submission -> artifacts -> evaluation -> report`

## Supporting platform services

- `Postgres`: durable run state, workflow metadata, and queue history once v2 moves beyond in-memory storage.
- `MinIO`: object storage for artifact bundles, reports, and optional dataset snapshots.
- `NATS`: internal event bus for status updates, notifications, and decoupled background processing.
- `Kubernetes Jobs`: bounded executors for workflow runs. Jobs should stay narrow, explicit, and tied to approved runner images.

## Design rule

Do not make v2 clever before making it legible. Schemas, workflow definitions, artifact contracts, and approval tiers should stay explicit and reviewable in Git.
