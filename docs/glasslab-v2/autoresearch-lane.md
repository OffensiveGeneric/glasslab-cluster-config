# Glasslab Autoresearch Lane

## What "autoresearch" means here

In Glasslab, "autoresearch" is not a free-form autonomous scientist. It is a bounded, backend-owned loop for exploring small methodology variants inside the existing v2 execution and approval model.

The first supported loop is:

`session or design context -> methodology drafts -> approved execution template -> short validation run -> score/compare -> keep/discard/review -> propose next bounded variants`

The first pass can also materialize a reviewable notebook scaffold from the current methodology draft:

`methodology draft -> deterministic notebook scaffold -> human review or later coding-model refinement`

This stays inside the current v2 rules:

- sessions remain the durable workspace
- `workflow-api` owns the state transitions
- `workflow-registry` remains the approval boundary
- evaluator and reporter remain deterministic
- OpenClaw stays a thin shell and summary surface

## How this differs from karpathy/autoresearch

This lane is intentionally narrower than `karpathy/autoresearch`.

Glasslab does **not** allow:

- arbitrary code mutation
- arbitrary shell access
- direct model-authored run manifests
- hidden planning state inside OpenClaw
- unrestricted browsing behind auth
- self-expanding tool surfaces

Instead, Glasslab autoresearch uses:

- explicit campaign records
- explicit methodology draft records
- explicit iteration and decision records
- deterministic backend endpoints
- approved execution templates only

## Bounded mutation surface

The mutation surface is structured and reviewable.

The first pass only mutates methodology choices such as:

- model family selection within the approved template
- baseline inclusion
- metric emphasis
- loss/objective emphasis when representable as structured notes
- resource profile within approved bounds
- bounded ablation toggles

Mutations are stored as structured diffs on methodology drafts. They are not code edits.

## Approval and safety rules

- all execution still goes through workflow-registry validation
- only approved templates with `execution_status=ready` are eligible
- the first lane targets currently approved bounded templates only
- the backend decides campaign state transitions; OpenClaw does not improvise them
- automatic decisions stay conservative and escalate when evidence is weak

## First supported loop

The first implementation supports:

1. create an autoresearch campaign from a research session plus an approved design draft
2. derive a seed methodology draft from that design
3. draft a small set of initial bounded methodology variants
4. launch one approved validation run for the next pending methodology variant
5. summarize the run state and any available metrics
6. record a deterministic decision:
   - `keep`
   - `discard`
   - `escalate_for_review`
7. produce a campaign summary plus proposed next bounded variants

The first execution target is intentionally narrow:

- `generic-tabular-benchmark`

This keeps the lane legible while reusing the existing run creation and validation spine.

## Persistence model

The first pass adds four explicit record types to `workflow-api` state:

- `MethodologyDraftRecord`
- `AutoresearchCampaignRecord`
- `AutoresearchIterationRecord`
- `AutoresearchDecisionRecord`

These records are stored alongside the rest of the session/intake/design/run state instead of creating a separate side architecture.

## Operator surface

If this lane is exposed through OpenClaw, keep it narrow and backend-owned. Good examples are:

- start autoresearch campaign
- get latest autoresearch campaign
- draft initial methodologies
- launch next autoresearch iteration
- summarize latest autoresearch state

Do not widen argumented free-form operator tooling to support this lane.

## Out of scope

The first pass does **not** attempt:

- general autonomous scientist behavior
- arbitrary repo creation
- unrestricted code synthesis and mutation
- unconstrained model planning
- direct OpenClaw ownership of the workflow
- automatic paper browsing behind institutional auth

## Current implementation note

This lane should be treated as the first bounded vertical slice for methodology exploration, not the finished research assistant. It is useful exactly because it is reviewable and narrow enough to fit the existing v2 architecture.

Notebook drafting in the first pass is deterministic. A stronger coding model may later help refine notebook cells, but the backend should still own:

- which methodology draft is being materialized
- which approved template it targets
- which structured inputs are embedded
- where the notebook is stored
