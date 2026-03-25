# Reporting Implementation Checklist

This note turns issue `#45` into a concrete implementation checklist.

The architectural question is already answered:

- reporting stays grounded in explicit artifacts
- the existing deterministic `reporter` service is the first implementation boundary

What remains is wiring and rollout discipline.

## Minimum Implementation Goal

Make it possible for the backend to produce an operator-facing report bundle from:

- run manifest
- run metrics
- optional evaluator output

without introducing a free-form reporting agent.

## Checklist

### 1. Keep Reporter Inputs Explicit

Reporter input should stay grounded in concrete files or payloads such as:

- `run_manifest.json`
- `metrics.json`
- optional evaluator output like `comparison.json`

Do not broaden the input contract to vague free-form context blobs.

### 2. Keep Reporter Output Deterministic

The first output should remain:

- stable Markdown memo / report text

Optional richer artifacts can come later, but deterministic Markdown is the baseline.

### 3. Define The Trigger Contract

`workflow-api` should own:

- deciding when report generation runs
- choosing the run or comparison scope
- passing grounded artifacts to the reporter

The reporter should own:

- rendering the report from those grounded inputs

### 4. Expose Result Location Clearly

The backend should make it obvious where the report lives:

- artifact index entry
- report path or URI
- report metadata tied to the run or comparison

That matters more than adding prose sophistication.

### 5. Fail Plainly On Missing Inputs

If the required artifacts are missing:

- do not invent a report
- surface an explicit incomplete-input result
- keep the missing-field signal operator-visible

### 6. Keep Model Help Optional And Downstream

If later prose enrichment is added:

- run it after deterministic report generation
- keep the deterministic report as the source of truth
- do not replace grounded report content with model-only prose

## Suggested Rollout

1. confirm reporter input/output contract in code and tests
2. define the `workflow-api` trigger path
3. expose resulting report location in backend responses or artifact listings
4. only later evaluate optional narrative rewriting

## Success Criteria

The issue is materially advanced when:

- report generation is backend-triggerable from grounded inputs
- result location is explicit
- missing-input behavior is explicit
- the deterministic path is in use before any narrative enrichment work starts

## Bottom Line

For reporting, the next win is boring integration, not more agency.

## References

- `reporting-boundary.md`
- `services/reporter/README.md`
- `stage-agent-rollout-order.md`
