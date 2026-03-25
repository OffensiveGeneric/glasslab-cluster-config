# Stage-Agent Rollout Order

This note turns the parent stage-agent roadmap into a rollout sequence.

The repo already contains:

- bounded service scaffolds
- `workflow-api` integration hooks and feature flags
- deployment manifests
- build/push and smoke-test paths

What remained unclear was:

- which stage should be enabled first
- what order reduces risk
- what evidence should be gathered before widening the rollout

## Recommended Rollout Order

### 1. Interpretation Agent First

Enable first:

- interpretation-agent only

Why first:

- it benefits strongly from model help
- it is not execution authority
- failure can fall back safely
- the output already has a concrete schema

Success proof:

- `workflow-api` logs show `stage-record-created stage=interpretation source=agent`
- invalid or unavailable responses fall back cleanly
- resulting records are more useful than deterministic-only interpretation

### 2. Intake Agent Second

Enable second:

- intake-agent

Why second:

- useful, but less critical than interpretation
- easy to fail closed
- mostly helps cleanup, normalization, and source classification

Success proof:

- deterministic fallback still behaves cleanly
- intake summaries are materially improved without breaking routing

### 3. Assessment Agent Third

Enable third:

- assessment-agent

Why third:

- it is closer to execution decisions than intake/interpretation
- backend policy checks still need to dominate
- benefits are meaningful only if the earlier stages are already producing good records

Success proof:

- recommendations remain policy-bounded
- unresolved fields are explicit
- fallbacks remain common whenever agent output is weak

### 4. Design Agent Fourth

Enable fourth:

- design-agent

Why fourth:

- this is the last model-assisted stage before deterministic manifest derivation
- it is the place where weak agent output becomes most dangerous if unchecked
- it should be enabled only after the earlier stages are proving useful

Success proof:

- design drafts remain inside approved workflow/resource/model constraints
- unresolved inputs remain explicit
- fallback remains the default on malformed or weak output

## What Should Stay Deterministic

Do not widen model ownership into:

- run preparation
- execution
- evaluation
- reporting artifact truth

Those boundaries should remain backend-owned and deterministic even if narrative enrichment is added later.

## Rollout Pattern

For each stage:

1. deploy service
2. leave feature flag off by default
3. enable one stage only
4. observe logs and resulting records
5. compare against deterministic-only baseline
6. only then widen to the next stage

## Anti-Pattern

Do not enable all four model-assisted stages at once.

That would make it impossible to tell:

- which stage actually improved outcomes
- where a bad record first entered the pipeline
- whether fallback behavior is actually working

## Suggested Short-Term Goal

The first realistic live bounded-agent milestone is:

- interpretation-agent deployed
- interpretation feature flag enabled
- stage-source logging confirming safe fallback behavior

That is enough to start learning from live use without turning the whole pipeline into a simultaneous experiment.

## References

- `stage-agent-pipeline.md`
- `stage-agent-api-changes.md`
- `interpretation-agent-service.md`
- `run-preparation-boundary.md`
