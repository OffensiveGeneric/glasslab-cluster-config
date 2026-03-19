# Intake, Design, And Validation-Run Implementation Plan

This note turns the bounded-agent architecture into a concrete first implementation plan.

The focus is narrow:

- intake record
- design draft
- validation run from design draft

The goal is to create the first real paper-to-validation path without depending on broad argumented tool reliability.

## Scope

This plan assumes the current v2 architecture remains intact:

- OpenClaw stays the front door
- `workflow-api` remains the orchestration backend
- the workflow registry remains the approval boundary
- evaluator and reporter remain deterministic post-run services

This plan does **not** try to add:

- broad multi-tool operator behavior
- free-form execution
- dynamic workflow generation outside the registry

## Product Goal

The first useful operator ladder should become:

1. start intake
2. inspect latest intake
3. create design draft from latest intake
4. create validation run from latest design
5. inspect latest run

This is enough to make the operator path feel materially closer to:

`paper or idea -> bounded validation experiment`

## Why Start Here

This path:

- fits the current no-arg tooling strategy
- maps cleanly onto existing backend responsibilities
- creates explicit stage records instead of hiding state in chat history
- does not require trustworthy argumented tool generation

## Existing Backend To Reuse

Current `workflow-api` already has:

- request schemas
- workflow-registry lookup
- validation
- persistence
- job submission
- run retrieval

Current workflow registry already has:

- explicit workflow IDs
- approval tiers
- expected artifacts
- resource profiles

So the plan should extend the current backend, not bypass it.

## New Backend Concepts

### 1. Intake Record

Purpose:

- persist the normalized starting point for a paper, note set, or research idea

Minimum fields:

- `intake_id`
- `created_at`
- `status`
- `source_type`
- `source_refs`
- `raw_request`
- `normalized_summary`
- `workflow_family_candidates`
- `notes`

Initial statuses:

- `created`
- `needs_clarification`
- `ready_for_design`

### 2. Design Draft

Purpose:

- persist the bounded draft that maps intake onto an approved workflow family

Minimum fields:

- `design_id`
- `intake_id`
- `created_at`
- `status`
- `workflow_id`
- `workflow_family`
- `objective`
- `declared_inputs`
- `candidate_models`
- `resource_profile`
- `expected_artifacts`
- `approval_tier`
- `design_notes`

Initial statuses:

- `drafted`
- `needs_review`
- `ready_for_run`
- `rejected`

### 3. Validation-Run Source Link

Purpose:

- make the relationship between a run and its design draft explicit

Minimum additions to run persistence:

- `source_design_id`
- `source_intake_id`
- `run_purpose`

`run_purpose` can initially be:

- `validation`

## Proposed API Surface

The first pass should stay narrow and backend-owned.

### Intake

#### `POST /intakes`

Create a new intake record.

Initial expected request shape:

- `raw_request`
- optional `source_refs`
- optional `source_type`

Backend should:

- normalize the request into a stored summary
- assign initial status
- store candidate workflow-family hints if available

#### `GET /intakes/latest`

Return the most recent intake record.

This mirrors the already successful "get latest" pattern used by runs.

### Design

#### `POST /design-drafts/from-latest-intake`

Create a design draft from the latest intake.

Backend should:

- fetch latest intake
- classify it against approved workflow families
- choose a bounded workflow candidate
- produce a draft with explicit workflow metadata
- reject the transition if no approved mapping is available

This should initially be deterministic where possible and conservative where ambiguous.

#### `GET /design-drafts/latest`

Return the most recent design draft.

### Validation Run

#### `POST /runs/from-latest-design-draft`

Create a validation run from the latest design draft.

Backend should:

- fetch latest design draft
- require `status=ready_for_run` or equivalent first-pass policy
- derive canonical run manifest
- submit the existing bounded Kubernetes Job flow
- persist run linked to design and intake

This is the natural successor to the current fixed validation payload path.

## OpenClaw Tool Surface

The first operator-facing tools should remain no-arg.

Recommended tools:

- `workflow_api_start_paper_intake`
- `workflow_api_get_last_intake`
- `workflow_api_create_design_draft_from_last_intake`
- `workflow_api_get_last_design_draft`
- `workflow_api_create_validation_run_from_last_design`

These should follow the existing successful pattern:

- repo-managed backend path
- no free-form argument generation in the operator turn
- backend persists the current stage record
- operator summarizes the result

## Suggested Responsibility Split

### `workflow-api`

Own:

- intake record schema
- design draft schema
- lifecycle transitions
- validation against workflow registry
- run derivation from design draft
- persistence

### Workflow Registry

Own:

- approved workflow families
- allowed models
- required inputs
- resource profiles
- artifact contracts
- approval tiers

### OpenClaw

Own:

- operator session
- narrow trigger tools
- human-facing summaries

### LLM Usage

Allow:

- intake summarization
- workflow-family hinting
- design-note drafting

Do not allow as sole source of truth:

- run manifest structure
- approval decisions
- resource-profile policy
- workflow-family allowlist

## Recommended Data Evolution Strategy

Do not over-design the schema at the first pass.

Recommended first rule:

- store records as explicit JSON payloads in backend persistence with stable top-level keys

That keeps early iteration easy while preserving a clear migration path later.

## Minimal Transition Rules

### Intake -> Design Draft

Allowed when:

- intake exists
- intake status is not terminal
- backend can map intake to an approved workflow family

Blocked when:

- no approved workflow match exists
- required source information is missing

### Design Draft -> Validation Run

Allowed when:

- design draft exists
- workflow ID is approved in registry
- resource profile is allowed
- required inputs are present or intentionally templated for validation mode

Blocked when:

- workflow ID is missing
- approval tier forbids unattended validation path
- required inputs cannot be resolved

## First-Pass Simplifications

To keep the first implementation realistic:

- allow a narrow `source_type` set such as `paper-note`, `plain-goal`, `paper-link`
- keep design-draft generation conservative
- prefer one approved workflow family over many fuzzy options
- support only validation-grade drafts at first
- keep literature extraction out of the first implementation if it slows the path too much

## Suggested Order Of Implementation

### Step 1

Add intake persistence and latest-intake retrieval to `workflow-api`.

Success looks like:

- backend can create and fetch intake records
- tests exist for create/get behavior

### Step 2

Add design-draft creation from latest intake.

Success looks like:

- backend can map a narrow intake into one approved workflow
- latest design draft is fetchable

### Step 3

Add run creation from latest design draft.

Success looks like:

- the current run submission path can be driven from stored design state instead of the fixed validation payload only

### Step 4

Add no-arg OpenClaw bindings for those transitions.

Success looks like:

- operator can move through intake -> design -> validation run with no argumented tools

## Test Strategy

The first pass should be tested mostly at the backend boundary.

Needed tests:

- create intake
- get latest intake
- create design draft from latest intake
- reject design creation when intake does not map to approved workflow
- create run from latest design draft
- reject run creation when design draft is not eligible

Operator tests should stay narrow:

- no-arg OpenClaw trigger succeeds
- backend state advances as expected

## What Can Wait

These can be deferred until the first path exists:

- broader literature-agent pipeline
- complex citation extraction
- argumented operator tools
- dynamic tool chaining
- multi-agent choreography inside OpenClaw itself

## Main Risks

### 1. Too Much LLM Logic In Draft Creation

Mitigation:

- keep workflow-family mapping bounded by registry
- keep backend validation final

### 2. Hidden State In OpenClaw

Mitigation:

- persist intake and design records in backend storage
- treat OpenClaw as a trigger and summary layer only

### 3. Schema Sprawl

Mitigation:

- keep first-pass records small
- add fields only when tied to a real stage transition

## Definition Of Success

This plan succeeds when:

- a user can start with a paper or idea
- the system creates a persisted intake record
- the system creates a persisted design draft mapped to an approved workflow
- the system creates a validation run from that draft
- the operator can inspect each stage through narrow no-arg actions

At that point, Glasslab will have its first real paper-to-validation backbone without needing trustworthy broad tool orchestration.
