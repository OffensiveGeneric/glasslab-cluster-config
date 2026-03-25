# Evaluation Boundary

This note resolves the shape of the evaluation stage in the backend stage-agent
pipeline.

The key decision is simple:

- evaluation should stay deterministic first
- any later model help should be strictly optional narrative enrichment after the
  deterministic comparison output already exists

## What Evaluation Owns

The evaluation stage compares grounded run outputs and produces a stable ranking
or comparison result.

Current concrete outputs already fit that role:

- `comparison.json`
- `summary.md`

Those come from `services/evaluator`.

## What Evaluation Should Not Own

Evaluation should not:

- choose which runs are allowed to exist
- reinterpret run manifests loosely
- invent missing metrics
- replace missing artifacts with model guesses
- directly schedule reruns

If a run bundle is incomplete, that should surface as incomplete evaluation
input, not as a place for free-form model repair.

## Current Recommended Service Shape

The existing `evaluator` service boundary is the right first implementation.

That means:

- no separate LLM-first evaluation agent is required now
- `workflow-api` should call deterministic evaluator logic using explicit run bundles
- operator-facing narrative can come later, but only from grounded evaluator output

## Internal Contract

The stable internal contract should be:

1. input:
   - one or more completed run bundle directories
2. required artifacts:
   - `run_manifest.json`
   - `metrics.json`
   - `status.json`
3. output:
   - `comparison.json`
   - `summary.md`

This matches the current `services/evaluator` implementation.

## Later Optional Enrichment

If model assistance is added later, it should be downstream of deterministic
evaluation and should never replace it.

Allowed future role:

- explain the comparison result in clearer operator-facing language

Disallowed future role:

- decide the winner without deterministic comparison
- synthesize metrics that were not produced by the runs
- override the comparison basis silently

## Workflow-API Relationship

`workflow-api` remains the owner of:

- deciding which completed runs are grouped for comparison
- triggering evaluator execution
- persisting or exposing evaluation results

The evaluator remains the owner of:

- deterministic comparison
- ranking basis
- grounded summary generation

## Issue Resolution Effect

This means issue `#42` should be treated as:

- formalizing the deterministic evaluation boundary
- improving the `workflow-api` to evaluator trigger contract if needed
- not inventing a new autonomous evaluation agent before there is a real need
