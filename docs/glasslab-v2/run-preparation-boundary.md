# Run-Preparation Boundary

This note resolves the intended shape of the run-preparation stage.

The key decision is:

- canonical run preparation stays inside `workflow-api`
- no separate free-form LLM-driven run-preparation service is needed in the
  first implementation

## What Run Preparation Owns

Run preparation is the step that turns a reviewable design draft into the final
bounded run request and canonical run manifest inputs.

That includes:

- selecting the approved workflow ID
- carrying forward the approved objective
- carrying forward declared inputs
- choosing requested models from the allowed set
- selecting the resource profile
- attaching source record references such as:
  - `source_design_id`
  - `source_intake_id`
- handing the final request to the bounded job-submission path

## What Run Preparation Should Not Own

Run preparation should not:

- invent missing required inputs
- override unresolved draft fields silently
- choose unapproved models
- widen resource profiles beyond registry policy
- submit work that still requires review

If a design draft is not `ready_for_run`, run preparation should fail closed.

## Current Implementation Reality

The current implementation in `workflow-api` already fits the intended boundary.

Current live code path:

- `POST /runs/from-latest-design-draft`

Current safety properties:

- latest design draft must exist
- design status must be `ready_for_run`
- workflow registry entry must exist
- final `RunCreateRequest` is derived from the approved design draft
- existing validation still applies before job submission

This means the current implementation is already pointing in the right
direction: deterministic derivation, not free-form planning.

## Recommended Ownership Split

`workflow-api` remains the owner of:

- canonical run request derivation
- final validation against registry constraints
- source-record linkage
- job submission handoff
- persisted run record creation

Design-stage services may assist earlier, but they should stop at producing a
reviewable design draft.

## Future Advisory Model Use

If model assistance is ever added here, it should remain advisory only.

Allowed future role:

- suggest missing review questions before a run is created

Disallowed future role:

- author the final canonical manifest without deterministic validation
- override operator-reviewed design inputs silently
- choose execution settings outside registry policy

## Issue Resolution Effect

This means issue `#41` should be treated as:

- preserving and documenting deterministic run-preparation behavior
- tightening `workflow-api` validation and manifest derivation as needed
- not inventing a separate autonomous run-preparation agent before there is a
  demonstrated gap
