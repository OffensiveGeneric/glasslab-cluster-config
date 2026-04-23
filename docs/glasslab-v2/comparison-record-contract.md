# Comparison Record Contract

This document defines the target Postgres record shape for evaluator and
comparison outputs.

The goal is to stop keeping comparison logic as an ad hoc response shape only,
and to make comparison results first-class durable records.

## Why This Exists

Right now Glasslab has:

- run records
- artifact files
- evaluator output conventions
- some comparison and summary response payloads

What is still missing is a clean, durable record for:

- which runs were compared
- under which evaluator
- with which comparison scope
- what summary was produced
- where the richer artifacts live

Without that, comparisons remain too transient and too tied to one response
path.

## Core Rule

Comparison is a record.

Comparison reports and summaries are files.

So:

- the comparison record belongs in Postgres
- comparison artifacts belong in MinIO or the artifact file plane

## Proposed Record Types

### `ComparisonRecord`

One durable record per comparison operation.

Minimum fields:

- `comparison_id`
- `created_at`
- `updated_at`
- `status`
- `comparison_type`
- `evaluator_type`
- `session_id` or `campaign_id`
- `workload_id` or `workflow_id`
- `run_ids`
- `baseline_run_id` when applicable
- `candidate_run_ids`
- `summary_metrics`
- `winner_run_id` when applicable
- `artifact_refs`
- `notes`

### `ComparisonScope`

Logical scope carried inside the record:

- `session`
- `campaign`
- `explicit-run-set`
- `latest-bounded-group`

This can be modeled as a field, not necessarily a separate table.

### `summary_metrics`

Structured summary fields that belong in Postgres because they are useful for
routing, ranking, and UI/API summaries.

Examples:

- `primary_metric_name`
- `baseline_value`
- `candidate_value`
- `delta`
- `winner_reason`
- `comparable`

This should stay compact.
Raw metric bundles still belong in `metrics.json`.

### `artifact_refs`

Structured refs to files such as:

- `comparison.json`
- `summary.md`
- `analysis_notebook.ipynb`

These refs belong in the record.
The files themselves do not.

## Suggested Schema Shape

This is the target logical shape:

```json
{
  "comparison_id": "cmp-123",
  "created_at": "2026-04-22T21:30:00Z",
  "updated_at": "2026-04-22T21:30:10Z",
  "status": "completed",
  "comparison_type": "model-selection",
  "evaluator_type": "art_retrieval_v1",
  "session_id": "session-abc",
  "campaign_id": "campaign-xyz",
  "workload_id": "metric-search-v0",
  "run_ids": ["run-a", "run-b"],
  "baseline_run_id": "run-a",
  "candidate_run_ids": ["run-b"],
  "summary_metrics": {
    "primary_metric_name": "retrieval_recall_at_10",
    "baseline_value": 0.71,
    "candidate_value": 0.76,
    "delta": 0.05,
    "winner_run_id": "run-b",
    "comparable": true
  },
  "artifact_refs": {
    "comparison_json": "s3://artifacts/cmp-123/comparison.json",
    "summary_md": "s3://artifacts/cmp-123/summary.md"
  },
  "notes": ["bounded two-run comparison"]
}
```

## Relationship To Existing Records

### `RunRecord`

`RunRecord` remains the record for one run.

It should not be overloaded to contain full comparison state.

At most, a run may carry lightweight links like:

- latest comparison id
- last compared at

### `OperationRecord`

`OperationRecord` remains an audit/control-plane record for an action.

It may reference a resulting `comparison_id`, but it is not the comparison
record itself.

### Autoresearch summaries

Current `AutoresearchCampaignSummaryResponse` fields like:

- `model_comparison`
- `score_summary`
- `comparison_summary`

should be treated as response-level projections built from durable records,
not as the only place comparison state exists.

## Record Boundaries

### Belongs in Postgres

- comparison identity
- run set membership
- scope
- evaluator type
- compact summary metrics
- winner/recommendation linkage
- artifact refs

### Belongs in artifact files

- rich comparison tables
- markdown narratives
- notebooks
- plots
- large per-run merged metric dumps

## Near-Term Implementation Delta

Before full generic experiment rollout, add:

1. a `ComparisonRecord` schema in `workflow-api`
2. persistence methods for saving/getting/listing comparison records
3. response projection helpers that build API summaries from those records
4. artifact ref persistence for evaluator outputs

This can start small:

- explicit-run comparisons
- autoresearch model comparisons

Then broaden later to more generic workload comparisons.

## Success Criteria

This contract is in effect when:

1. a comparison can be reloaded without recomputing it from files alone
2. the API can show “what was compared and what won” from Postgres
3. evaluator artifacts are linked by reference, not re-parsed as the source of
   truth

## Bottom Line

Comparison should become a first-class record type in Postgres.

Its rich outputs should remain files.

That is the clean boundary between durable control-plane state and evaluator
artifacts.
