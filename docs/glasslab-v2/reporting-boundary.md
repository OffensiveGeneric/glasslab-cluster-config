# Reporting Boundary

This note resolves the intended shape of the reporting stage.

The key decision is:

- reporting should stay grounded in explicit run and evaluation artifacts
- the current deterministic `reporter` service is the right first boundary

## What Reporting Owns

Reporting turns grounded backend artifacts into a stable operator-facing memo.

Current concrete inputs:

- `run_manifest.json`
- `metrics.json`
- optional evaluator output such as `comparison.json`

Current concrete output:

- Markdown memo / report text

That is already implemented in `services/reporter`.

## What Reporting Should Not Own

Reporting should not:

- invent results missing from the run bundle
- reinterpret metrics as if they came from a different workflow
- override evaluator ranking silently
- decide what should be executed next

If the upstream artifacts are incomplete, the report should say that plainly.

## Current Recommended Service Shape

The existing `reporter` is the correct first implementation boundary.

That means:

- no separate autonomous reporting agent is required now
- `workflow-api` can later trigger deterministic report generation from explicit
  artifacts
- any later model help should stay downstream of grounded inputs

## Later Optional Enrichment

If model assistance is added later, it should stay bounded.

Allowed future role:

- rewrite or summarize the grounded report for different operator audiences

Disallowed future role:

- hallucinate metrics or conclusions not present in the artifacts
- replace the deterministic report as the source of truth

## Workflow-API Relationship

`workflow-api` remains the owner of:

- deciding when reporting should run
- choosing which run or evaluation artifacts are in scope
- exposing resulting reports through backend APIs

The reporter remains the owner of:

- deterministic memo rendering from grounded artifacts

## Issue Resolution Effect

This means issue `#45` should be treated as:

- formalizing the deterministic reporting boundary
- tightening the `workflow-api` to reporter trigger contract if needed
- delaying any model-backed prose enrichment until the deterministic path is in
  regular use
