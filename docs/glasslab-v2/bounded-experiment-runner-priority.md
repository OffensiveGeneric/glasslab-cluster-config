# Bounded Experiment-Runner Priority

This note resets the near-term priority for Glasslab v2.

The current problem is not a lack of possible features. It is a lack of a narrow, dependable loop that can keep producing useful experiment work while operators are away.

## Priority

The main near-term product should be:

`manual source -> bounded interpretation -> bounded methodology variants -> approved run template -> validation run -> comparison -> keep/discard/review`

That loop should create value even if:

- literature search stays weak
- chat routing is still imperfect
- stage-agent quality is mixed
- larger external models are still being evaluated

## What Changes

For now, Glasslab should optimize for:

- strong experiment-runner behavior
- broad knowledge of techniques
- explicit bounded outputs
- durable comparison state
- unattended iteration within approved limits

Glasslab should **not** currently optimize for:

- clever literature discovery
- broad chat orchestration
- free-form research planning
- unconstrained code or manifest generation
- adding more user-facing commands before the experiment path is solid

## Source Posture

Literature support remains useful, but it should be narrowed for now.

Near-term supported source posture:

- manual paper add
- manually attached source URLs
- validated fetched source documents
- interpretation from stored source documents

Nice-to-have but de-prioritized:

- automatic broad literature search
- aggressive provider expansion
- trying to make search itself feel intelligent before experiment execution is dependable

The product can still ingest papers and source documents, but that should mainly serve interpretation and methodology drafting rather than becoming the primary milestone.

## Interpretation Boundary

Interpretation should become more bounded, not more open-ended.

The output of interpretation should be useful precisely because it is constrained into fields the cluster can act on.

Interpretation should produce:

- objective
- task framing
- candidate model families
- candidate baselines
- candidate metrics
- candidate losses or distance objectives
- dataset and split hints
- runtime and package hints
- preferred workflow template
- preferred resource profile
- explicit risks
- bounded mutation axes for autoresearch

Interpretation should **not** be treated as:

- a free-form research essay
- a workflow planner
- an authority to invent execution shapes outside the registry

## Technique Knowledge Goal

The right kind of "more knowledge" is:

- methodology knowledge
- model-family knowledge
- baseline knowledge
- metric knowledge
- split/validation knowledge
- common failure-mode knowledge

This knowledge should feed:

- methodology drafting
- autoresearch mutation choices
- preflight checks
- run comparison summaries

It should not directly expand the execution surface.

## Autoresearch Role

Autoresearch should keep a small part of the Karpathy spirit:

- try more bounded methodology variants than a human has time for
- keep working while operators are away
- compare outcomes continuously
- persist evidence and next-step proposals

But it should stay within hard limits:

- approved templates only
- structured mutations only
- durable iteration records
- deterministic keep/discard/review decisions when possible
- escalation when evidence is weak

Autoresearch should be treated as:

- bounded methodology exploration

not:

- general autonomous science

## Immediate Execution Priorities

1. Make interpretation output map cleanly into approved run templates.
2. Make preflight catch split, runtime, package, and resource mismatches.
3. Make `!run` and `!launch-iteration` dependable once prerequisites are satisfied.
4. Make campaign summaries read as "best current method" reports.
5. Keep manual source intake enough to support those steps.

## De-prioritized For Now

- broad automated literature search as a product headline
- new ingestion source classes unless they directly improve methodology knowledge
- more OpenClaw cleverness
- more command-surface growth without experiment payoff
- putting experimental large-model backends on the critical path

## Practical Rule

If a change does not improve:

- method selection
- bounded run creation
- run comparison
- unattended iteration
- or experiment reliability

it is probably not the current priority.
