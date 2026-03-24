# Qwen Fit For Stage Agents

This note exists to answer one practical question:

Which proposed Glasslab backend stage agents are a good fit for the current local Qwen path, and which ones are not?

Current local model context:

- OpenClaw and the current local reasoning path use `Qwen/Qwen3-4B-Instruct-2507`
- served locally through `vLLM`
- proven useful for narrow no-arg operator flows
- not yet proven reliable for trusted structured tool arguments

That means the right way to use Qwen is not:

- "make it the hidden workflow brain"

The right way to use it is:

- "let it help with bounded interpretation and explanation, then validate deterministically"

## Good Current Fits

These are stage-agent tasks that the current Qwen path is likely good enough to assist with.

### Paper Intake Cleanup

Examples:

- normalize a pasted request
- compress notes into a short summary
- classify whether the source is a paper link, paper note, or plain goal

Why this fits:

- low consequence
- easy to validate
- failures are recoverable

### Paper Interpretation Drafts

Examples:

- identify likely method family
- extract likely dataset mentions
- identify likely evaluation target
- produce candidate workflow-family suggestions

Why this fits:

- useful fuzzy work
- can be constrained to a schema
- backend can reject or require review if confidence is poor

### Explanatory Notes

Examples:

- explain why a draft needs review
- summarize why a paper does not cleanly map to a current workflow family
- produce operator-facing status language

Why this fits:

- these are not primary control decisions
- narrative quality matters more than exact machine control

### Draft Report Enrichment

Examples:

- narrative summary for a completed run
- commentary on metrics and artifact bundle contents
- explanatory text for a notebook or report section

Why this fits:

- deterministic artifacts already exist underneath
- the model is enriching a grounded result, not inventing system state

## Borderline Fits

These can use Qwen, but only with strong validation and clear fallback behavior.

### Workflow-Family Ranking

Examples:

- choose among a small candidate set from the approved registry

Why borderline:

- useful place for model assistance
- but still close to execution control
- best treated as "suggest and score," not "decide unilaterally"

Recommended pattern:

- backend supplies the candidate set
- Qwen ranks or comments
- deterministic rules or later review decide whether to advance

### Replicability Assessment Drafts

Examples:

- suggest whether a paper is likely reproducible within current workflow families
- identify unresolved fields that block safe execution

Why borderline:

- very useful reasoning task
- but the consequences of being wrong are higher

Recommended pattern:

- Qwen drafts the assessment
- backend validates fields and approval-tier implications
- unresolved or low-confidence assessments stay in `needs_review`

## Poor Fits Right Now

These should not rely on the current Qwen path as the main source of truth.

### Final Approval Decisions

Examples:

- whether a run is approved for execution
- whether a new workflow family is safe

Why not:

- too high consequence
- needs deterministic policy and human review where required

### Canonical Run Manifest Authority

Examples:

- final model list
- final dataset URIs
- final resource profile
- final runner image selection

Why not:

- these are execution-control fields
- the current local path has not proven trustworthy enough for this level of structured control

### Infrastructure Mutation

Examples:

- cluster changes
- storage changes
- image deployment changes

Why not:

- not an appropriate trust level
- belongs to explicit tooling and human-reviewed operations

### Broad Multi-Step Autonomous Orchestration

Examples:

- one model run coordinating the whole research pipeline from intake to execution

Why not:

- current model quality is not the only blocker
- the current OpenClaw control surface is also not set up for precise structured control
- backend stage records are the better system design

## Recommended Pattern

The right near-term Glasslab pattern is:

1. Qwen interprets, summarizes, or drafts
2. the backend validates the result against schema and policy
3. the stage either advances or stops for review

That means:

- Qwen proposes
- deterministic logic decides

## Practical Conclusion

The current Qwen path is good enough to start building backend stage agents now, as long as those agents are assigned the right jobs.

Use it for:

- interpretation
- classification
- summarization
- grounded report language

Do not use it as the sole authority for:

- execution approval
- canonical manifests
- infrastructure change
- unconstrained orchestration

This is enough to move Glasslab forward without waiting for a dramatically stronger local model.
