# Evaluation Implementation Checklist

This note turns issue `#42` into a concrete implementation checklist.

The architecture decision is already made:

- evaluation stays deterministic first
- the existing `evaluator` service is the correct first boundary

What remains is the boring integration work.

## Minimum Implementation Goal

Make it possible for the backend to compare completed runs using grounded run
bundles and expose deterministic evaluation outputs without introducing a fuzzy
evaluation agent.

## Checklist

### 1. Keep Evaluator Inputs Explicit

The evaluator input contract should stay grounded in explicit run bundles with:

- `run_manifest.json`
- `metrics.json`
- `status.json`

Do not widen this to vague prompt context or model-generated comparison inputs.

### 2. Keep Evaluator Outputs Deterministic

The baseline outputs remain:

- `comparison.json`
- `summary.md`

Those are the source of truth for comparison.

### 3. Define The Trigger Contract

`workflow-api` should own:

- selecting the completed runs to compare
- deciding when evaluation runs
- passing explicit run bundle references to the evaluator

The evaluator should own:

- deterministic comparison
- summary generation from grounded artifacts

### 4. Expose Evaluation Results Clearly

The backend should make it explicit where the evaluation results are:

- evaluation artifact entries
- run comparison metadata
- stable paths or URIs for `comparison.json` and `summary.md`

### 5. Fail Plainly On Incomplete Inputs

If required artifacts are missing:

- do not invent a comparison
- return an explicit incomplete-input result
- keep the missing-artifact signal operator-visible

### 6. Keep Narrative Enrichment Optional

If later model help is added:

- run it after deterministic evaluation exists
- keep `comparison.json` and deterministic `summary.md` authoritative
- do not let model prose replace grounded comparison outputs

## Suggested Rollout

1. confirm evaluator contract in code and tests
2. define `workflow-api` trigger and storage path
3. expose evaluation artifact locations in backend responses
4. only later consider optional narrative restatement

## Success Criteria

The issue is materially advanced when:

- deterministic evaluator execution is backend-triggerable
- evaluation result location is explicit
- incomplete-input behavior is explicit
- the deterministic path is used before any model-backed explanation work starts

## Bottom Line

For evaluation, the next win is backend wiring and explicit artifact exposure,
not a new agent.

## References

- `evaluation-boundary.md`
- `services/evaluator/README.md`
- `reporting-implementation-checklist.md`
