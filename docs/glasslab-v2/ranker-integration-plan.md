# Ranker Integration Plan

This note turns issue `#23` from "ranker exists" into "how should `workflow-api` actually use it?"

The ranker is already live on `.12` and already has a bounded API.

What remains is a backend-owned integration rule that keeps ranking advisory and fail-closed.

## First Integration Target

The first integration target should be:

- workflow-family selection during intake handling

Not:

- design approval
- run creation
- tool choice
- execution authority

## Caller Ownership

`workflow-api` should remain the owner of:

- candidate generation
- ranker invocation
- acceptance thresholds
- fallback behavior
- persistence of the resulting intake record

The ranker should remain a scoring service, not a decision engine.

## Suggested Integration Point

The cleanest first seam is inside the intake path:

- deterministic candidate generation happens first
- bounded candidate list is sent to the ranker
- ranked result is used to reorder or narrow candidates
- the final persisted intake still comes from `workflow-api`

In practical terms:

- `POST /intakes` remains the public entrypoint
- ranker use is hidden behind a feature flag and internal config

## Acceptance Rules

Use the ranker result only if:

- returned candidate IDs match the offered set
- the top score is above a configured threshold
- the top score is sufficiently separated from the next score

Otherwise:

- keep deterministic ordering
- or leave the intake unresolved for later review

## Persistence Recommendation

Do not let the ranker silently replace backend reasoning.

Persist enough metadata to explain what happened:

- whether ranking was used
- ranked candidate order
- top score
- fallback reason if ranker output was ignored

This can start as log-only metadata if schema changes are not yet justified.

## Failure Rules

The ranker must fail closed.

Treat these as fallback conditions:

- network failure
- timeout
- malformed response
- candidate mismatch
- low confidence
- ambiguous top scores

The fallback should be:

- deterministic candidate ordering
- or unresolved intake state if deterministic confidence is also weak

## Suggested Config Surface

`workflow-api` will likely need:

- `GLASSLAB_WORKFLOW_API_RANKER_ENABLED`
- `GLASSLAB_WORKFLOW_API_RANKER_URL`
- `GLASSLAB_WORKFLOW_API_RANKER_TIMEOUT_SECONDS`
- `GLASSLAB_WORKFLOW_API_RANKER_MIN_TOP_SCORE`
- `GLASSLAB_WORKFLOW_API_RANKER_MIN_SCORE_GAP`

## Recommended Rollout

1. add ranker config surface to `workflow-api`
2. add internal client helper for `POST /rank/workflow-family`
3. keep deterministic candidate generation as the baseline
4. use the ranker only to reorder or narrow candidate lists
5. log whether ranker output was accepted or ignored
6. compare behavior before widening usage

## What Not To Do First

Do not first:

- let the ranker create workflow IDs that were not offered
- let the ranker approve execution
- use the ranker as a hidden general-purpose reasoning service

That would throw away the main safety value of the current backend-first architecture.

## Bottom Line

The right first integration is:

- bounded
- advisory
- feature-flagged
- backend-owned
- easy to disable

## References

- `ranker-service-shape.md`
- `stage-agent-api-changes.md`
- `../machine-state-2026-03-24.md`
