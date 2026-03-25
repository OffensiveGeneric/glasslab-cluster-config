# Ranker Implementation Checklist

This note turns issue `#23` into concrete backend work.

The ranker already exists as a bounded service.

What remains is a safe `workflow-api` integration path that keeps the ranker advisory and easy to disable.

## First integration checklist

- keep the first ranker use limited to workflow-family selection during intake handling
- generate the candidate family set deterministically inside `workflow-api` before any ranker call
- send only bounded candidate IDs and intake context to the ranker
- accept ranker output only when returned IDs exactly match the offered set
- keep deterministic ordering when the ranker fails, times out, or returns ambiguous scores

## Config checklist

- add `GLASSLAB_WORKFLOW_API_RANKER_ENABLED`
- add `GLASSLAB_WORKFLOW_API_RANKER_URL`
- add `GLASSLAB_WORKFLOW_API_RANKER_TIMEOUT_SECONDS`
- add `GLASSLAB_WORKFLOW_API_RANKER_MIN_TOP_SCORE`
- add `GLASSLAB_WORKFLOW_API_RANKER_MIN_SCORE_GAP`

## Validation checklist

- reject responses that invent candidate IDs not present in the offered set
- reject responses with malformed score payloads
- reject responses whose top score is below the configured threshold
- reject responses whose top score is too close to the next candidate
- log whether the ranker result was accepted or ignored

## Persistence checklist

- keep ranker output advisory rather than authoritative
- persist or log ranked candidate order and top score when accepted
- log an explicit fallback reason when ranker output is ignored
- do not let the ranker silently create a workflow ID that deterministic logic did not offer

## Rollout checklist

1. add config surface in `workflow-api`
2. add one internal client helper for `POST /rank/workflow-family`
3. wire the helper behind a feature flag in the intake path
4. compare ranker-assisted and deterministic outcomes before widening usage
5. only then consider later ranker use in interpretation or design review

## Close rule

Issue `#23` should be considered materially advanced when:

- `workflow-api` can call the ranker behind a feature flag
- candidate validation and fail-closed fallback are implemented
- logs or records show whether ranker output was accepted or ignored
- ranker use remains limited to advisory workflow-family selection
