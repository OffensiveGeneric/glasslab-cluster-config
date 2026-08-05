# Investigation API v1

Status: current first executable vertical slice

Date: 2026-07-23

## Decision

An investigation is Glasslab's product-level research record. It is not a
wrapper around a legacy research session or design draft.

The v1 domain is:

```text
investigation
  -> hypotheses
  -> append-only execution-graph plans
  -> immutable approval snapshot
  -> dependency-checked bounded runs
  -> verified artifact bundles
  -> evidence-backed claim
```

Research-session, intake, paper-pipeline, and `DesignDraftRecord` routes remain
compatibility features. They may create generic runs, but no investigation API
depends on them.

## Current API

| Method and path | Effect |
| --- | --- |
| `POST /investigations` | Create a first-class investigation. |
| `GET /investigations/{investigation_id}/context` | Read the investigation, current plan, approved plan, and linked runs. |
| `POST /investigations/{investigation_id}/hypotheses` | Add a hypothesis under exploratory/confirmatory integrity rules. |
| `POST /investigations/{investigation_id}/plans` | Append an immutable execution-graph plan revision. |
| `POST /investigations/{investigation_id}/plan-approvals` | Freeze an explicit plan and the current research state by SHA-256. |
| `POST /investigations/{investigation_id}/runs` | Launch one named execution from an explicit active approval. |
| `POST /investigations/{investigation_id}/claims` | Store a claim tied to exact, ingested run artifacts. |

There are no hidden `latest` lookups in the plan, approval, or run write path.
The caller names `investigation_id`, `plan_id`, `approval_id`, and
`execution_id`.

## Workspace Plan

An executable plan freezes an acyclic graph of one or more execution nodes.
Each node declares its dependencies and freezes:

- an immutable task bundle URI and SHA-256
- an immutable source bundle URI and SHA-256
- working directory and command
- network policy
- a data-access scope
- digest-pinned dataset bindings and the scopes allowed to see each binding
- registered workload and experiment type
- wall-clock budget
- required and optional artifacts
- evaluator and guardrail contracts

Images, Kubernetes resource limits, service accounts, and the container
entrypoint come from the workload registry. A plan cannot override them.
At launch, Glasslab exposes only bindings that permit the selected execution's
data-access scope. A dependent node cannot launch until every declared
predecessor has a successful run under the same approval.

Research workspace Jobs do not mount either shared PVC at its root. They
receive one read-only Kubernetes `subPath` mount per approved task, source, or
dataset asset, plus one writable artifact `subPath` for their own `run_id`.
Workspace code therefore cannot browse hidden datasets or other runs through
the shared volumes.

Task and dataset assets may come from the approved dataset plane. Generated
source and derived inputs may come from an exact, digest-pinned artifact path;
the job still receives only that file rather than the artifacts-plane root.

The initial execution workload is `research-workspace-cpu-v1`. It runs a
source bundle produced by a researcher or research agent. Code generation
happens before plan approval; approval freezes the generated code before
execution.

## Integrity Rules

Plans are append-only. Editing a plan means creating another revision.

An approval hashes canonical JSON containing:

- investigation identity, question, and mode
- every current hypothesis record
- the complete immutable plan

Exploratory hypothesis changes keep approval history but clear the active
approval. Confirmatory hypotheses freeze after approval, and a confirmatory
plan cannot be replaced after execution begins.

Every run record stores:

- `investigation_id`
- `source_plan_id`
- `source_approval_id`
- `source_execution_id`
- `plan_sha256`

A successful terminal bundle cannot be ingested until every required artifact
exists as a real, non-symlinked path inside the run directory. Ingestion hashes
each file and marks the run's artifact bundle verified. Generic callers may
still report external result references, but those unverified reports cannot
support investigation claims. Bundle ingestion is one-way and idempotent; claim
creation rechecks the cited file against its stored digest and rejects content
drift.

Claims may cite only:

- hypotheses from the same investigation
- terminal runs from the same investigation
- artifact names and SHA-256 content digests from verified terminal bundles

Supported or refuted claims require a successful run. Inconclusive claims may
preserve evidence from a failed or rejected terminal run. A supported or
refuted claim is also rejected when the run is missing its approved primary
metric or fails any approved evaluator guardrail.

## Runner Boundary

`research-workspace-cpu-v1` verifies task, source, and dataset digests; rejects
archive traversal and links; rejects symlink artifacts; executes one command;
and writes a terminal bundle. Its pods:

- have a Kubernetes active deadline derived from the approved budget
- do not receive a service-account token
- cannot escalate privileges and drop Linux capabilities
- use the runtime-default seccomp profile
- can mount only declared input files and their own run output directory
- receive a deny-egress NetworkPolicy when `network_policy` is `none`

The CPU image includes a pinned classical Python data-science environment for
the Adult Income and Wine starting tasks. A GPU workspace image is a later
extension of the same contract.

## Trust Boundary

This slice verifies execution inputs, stage-scoped data exposure, dependency
order, artifact completeness, and artifact content identity. It does not yet
independently reproduce reported metrics or apply a full rubric evaluator.

The next slice is solver/evaluator separation:

1. a research agent receives the visible task and produces a source bundle;
2. Glasslab freezes that bundle;
3. the workspace runner executes it;
4. a separate evaluator receives the frozen submission and hidden evaluation
   contract;
5. claims use evaluator-produced evidence.
