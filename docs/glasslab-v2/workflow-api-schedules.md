# Workflow API Schedule Endpoints

This note documents the first stored schedule endpoints now present in `workflow-api`.

It exists to make issue `#30` concrete at the API-contract level.

## Purpose

These endpoints do not execute unattended work by themselves yet.

They create and manage stored schedule records so unattended behavior can be built as explicit backend state instead of hidden prompt logic.

## Current Schedule Families

### Digest schedules

Approval tier:

- `tier-1-read-only`

Purpose:

- store recurring read-only summary or digest intent

Current endpoints:

- `POST /digest-schedules`
- `GET /digest-schedules`
- `POST /digest-schedules/{schedule_id}/disable`

Stored fields include:

- `schedule_id`
- `status`
- `operation_type=digest`
- `approval_tier=tier-1-read-only`
- `owner`
- `cron_expr`
- `scope_filter`
- `digest_kind`

### Approved rerun schedules

Approval tier:

- inherited from the latest accepted run

Purpose:

- store recurring rerun intent only for a latest run that is both:
  - `tier-2-approved-execution`
  - `succeeded`

Current endpoints:

- `POST /approved-rerun-schedules/from-latest-run`
- `GET /approved-rerun-schedules`
- `POST /approved-rerun-schedules/{schedule_id}/disable`

Stored fields include:

- `schedule_id`
- `status`
- `operation_type=approved-rerun`
- `owner`
- `cron_expr`
- `workflow_id`
- `source_run_id`
- `source_design_id`
- `allowed_dataset_uri`
- `allowed_model_ids`
- `allowed_runner_image`
- `resource_profile`

## Current Guardrails

The approved rerun schedule path currently refuses to create a schedule unless:

- a latest run exists
- that run resolved to `status=succeeded`
- that run has `approval_tier=tier-2-approved-execution`

This keeps the stored schedule path aligned with the current approval model.

## What Is Not Implemented Yet

These endpoints do not yet provide:

- scheduler execution workers
- `run-now` execution endpoints
- digest materialization jobs
- recurring rerun job submission from the stored schedules
- OpenClaw schedule-management tools

That missing work is intentional.

The current stage is:

- first store explicit schedule records
- then decide how execution workers should consume them

## Why This Matters

This is the right backend-first shape for unattended operations because:

- schedules become explicit stored records
- approval tiers stay inspectable
- execution can fail closed later
- OpenClaw can remain a narrow front door instead of becoming the hidden scheduler brain
