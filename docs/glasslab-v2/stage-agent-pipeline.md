# Stage-Agent Pipeline

This note sharpens the current Glasslab v2 direction:

- OpenClaw remains ingress and operator interaction
- `workflow-api` remains the system-of-record for workflow state and stage transitions
- backend agents do bounded work on explicit records
- Kubernetes Jobs remain the bounded execution layer

The system should move toward a pipeline of specialized backend agents rather than a single general chat agent trying to improvise the whole process.

## Current Status

As of 2026-03-25, this roadmap is no longer purely conceptual.

Repo-backed progress now splits into two categories:

- bounded service scaffolds now exist for:
  - intake
  - interpretation
  - replicability assessment
  - design drafting
- deterministic boundary decisions are now explicit for:
  - run preparation
  - execution
  - evaluation
  - reporting

That means the remaining work is primarily:

- wiring the first bounded services into `workflow-api`
- adding Kubernetes manifests and service wiring
- validating live model-backed behavior only where it actually helps

## Goal

Turn:

- paper
- idea
- benchmark request

into:

- an intake record
- a design draft
- an approved run
- execution artifacts
- an evaluation/report bundle

with minimal operator friction and clear stage boundaries.

## Core Principle

Each agent should own one narrow stage and communicate through explicit state, not chatty hidden reasoning.

Good handoff mechanisms:

- `workflow-api` records
- NATS messages
- shared artifacts
- Kubernetes Jobs

Bad handoff mechanisms:

- implicit chat history
- one long prompt pretending to be a whole workflow engine
- unvalidated free-form tool arguments

## Proposed Agents

### 1. Paper Intake Agent

Purpose:

- normalize paper links, notes, and operator-supplied context into an intake record

Inputs:

- URL
- pasted notes
- operator summary

Outputs:

- intake record
- normalized source refs
- initial summary

LLM use:

- optional and bounded
- useful for summary cleanup and source classification

Deterministic checks:

- source format validation
- duplicate detection
- required fields present

Current repo state:

- bounded scaffold exists under `services/intake-agent`
- `workflow-api` config surface is reserved

### 2. Paper Interpretation Agent

Purpose:

- extract the method, likely datasets, evaluation target, and likely workflow family

Inputs:

- intake record
- fetched paper text or notes

Outputs:

- structured interpretation record
- candidate workflow families
- extracted claims and experiment hints

LLM use:

- appropriate
- this is one of the best places for model assistance

Deterministic checks:

- output schema validation
- candidate family must be in approved registry set

Current repo state:

- bounded scaffold exists under `services/interpretation-agent`
- `workflow-api` config surface is reserved

### 3. Replicability Assessment Agent

Purpose:

- decide whether the paper can map cleanly to an approved workflow shape

Inputs:

- interpretation record
- workflow registry

Outputs:

- replicability assessment
- unresolved fields
- recommended next step:
  - proceed
  - needs review
  - reject

LLM use:

- optional
- could help explain why a paper does or does not fit

Deterministic checks:

- approval-tier rules
- required workflow inputs identified or explicitly unresolved

Current repo state:

- bounded scaffold exists under `services/assessment-agent`
- `workflow-api` config surface is reserved

### 4. Design Draft Agent

Purpose:

- convert intake + interpretation + assessment into a design draft

Inputs:

- intake record
- interpretation record
- replicability assessment

Outputs:

- design draft
- declared inputs
- unresolved inputs
- expected artifacts

LLM use:

- appropriate for explanation and candidate design notes

Deterministic checks:

- design must map to a real workflow family
- unresolved fields must be explicit
- only approved models/resource profiles may appear

Current repo state:

- bounded scaffold exists under `services/design-agent`
- `workflow-api` config surface is reserved

### 5. Run Preparation Agent

Purpose:

- convert an approved design draft into a canonical run manifest

Inputs:

- approved design draft
- workflow registry entry

Outputs:

- run manifest
- accepted run record

LLM use:

- ideally none

Deterministic checks:

- strict schema validation
- registry-backed allowed values only

Current repo state:

- should remain a deterministic `workflow-api` boundary
- see `run-preparation-boundary.md`

### 6. Execution Agent

Purpose:

- submit the run to Kubernetes and track execution lifecycle

Inputs:

- accepted run manifest

Outputs:

- Job submission receipt
- live status updates
- artifact bundle

LLM use:

- none

Deterministic checks:

- job spec construction
- artifact contract enforcement

Current repo state:

- should remain a deterministic `workflow-api` plus `JobSubmitter` boundary
- see `execution-boundary.md`

### 7. Evaluation Agent

Purpose:

- compare completed runs and produce deterministic evaluation output

Inputs:

- completed run bundles
- metrics
- status

Outputs:

- comparison output
- summary output

LLM use:

- optional for narrative summary only

Deterministic checks:

- metric comparison logic
- workflow-family compatibility

Current repo state:

- should remain the deterministic `evaluator` boundary first
- see `evaluation-boundary.md`

### 8. Reporting Agent

Purpose:

- produce the operator-facing result bundle

Inputs:

- run manifest
- metrics
- evaluation output
- supporting artifacts

Outputs:

- `report.md`
- optional richer presentation artifact such as a Jupyter notebook

LLM use:

- useful for concise narrative summaries

Deterministic checks:

- required report sections
- artifact references must exist

Current repo state:

- should remain the deterministic `reporter` boundary first
- see `reporting-boundary.md`

## Notebook Output Idea

A good future target is for final artifacts to optionally include a generated Jupyter notebook.

That notebook could contain:

- run context
- loaded metrics and artifact references
- deterministic Python visualizations
- comparison tables
- lightweight narrative commentary

This is attractive because it makes the final result more inspectable and more useful for real research follow-up than a plain text report alone.

Important constraint:

- the notebook should be generated from structured artifacts and deterministic templates where possible
- it should not become a hidden execution surface with arbitrary code generation by default

## How Agents Should Coordinate

Preferred coordination:

- `workflow-api` stores stage records
- a worker picks up the next eligible record
- the worker writes a new record or artifact bundle
- `workflow-api` advances stage state if validation passes

Possible transport choices:

- synchronous HTTP between services
- NATS for async stage notifications
- Kubernetes Jobs for bounded heavy work

The system does not require agent-to-agent chat.

## Role Of OpenClaw

OpenClaw should stay at the edge.

It should do:

- operator ingress
- summaries
- safe no-arg stage triggers
- status inspection

It should not be the hidden place where all backend workflow logic lives.

## Why This Direction Fits Glasslab

This path:

- reduces dependence on argumented tool calls
- matches the current no-arg success pattern
- preserves operator usability
- makes parallel backend work more plausible
- keeps the system auditable

This is a better match for the current hardware and model limitations than trying to force one live chat agent to orchestrate the whole research pipeline.

## Recommended Next Implementation Order

1. wire the interpretation-agent into `workflow-api` behind a feature flag
2. wire the intake-agent the same way
3. wire the assessment-agent
4. wire the design-agent
5. add explicit evaluator and reporter trigger contracts
6. only then revisit whether any later enrichment actually needs model help
