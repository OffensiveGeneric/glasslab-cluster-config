# Ranker Service Shape

This note turns issue `#23` into a concrete first implementation shape.

## Why A Ranker Now

The current system already has:

- a deterministic backend in `workflow-api`
- a narrow operator gateway in OpenClaw
- live evidence that broad argumented tool use is still unreliable
- emerging Apple-silicon sidecar capacity outside the cluster

That makes a bounded ranker service a better next model-serving target than broader OpenClaw autonomy.

## First Job

The first ranker use should be:

- workflow-family selection from intake

Why this is the best first fit:

- the candidate set is naturally small
- the backend can generate or constrain the candidate set before ranking
- acceptance can stay backend-owned
- failure can stay safe by falling back to clarification or deterministic routing

## What The Ranker Should Receive

Input:

- intake record summary
- small candidate list of approved workflow families
- optional backend-extracted features or hints

Example shape:

```json
{
  "request_id": "intake-123",
  "query": "Compare a paper's claimed method against an approved validation workflow.",
  "candidates": [
    {
      "workflow_id": "literature-to-experiment",
      "summary": "Derive a bounded experiment design from a paper or literature notes."
    },
    {
      "workflow_id": "generic-tabular-benchmark",
      "summary": "Run an approved tabular benchmark against a declared dataset."
    }
  ]
}
```

## What The Ranker Should Return

Output:

- ranked candidates
- numeric or ordinal confidence
- short rationale string

Example shape:

```json
{
  "request_id": "intake-123",
  "ranked_candidates": [
    {
      "workflow_id": "literature-to-experiment",
      "score": 0.91,
      "reason": "The request begins from paper interpretation rather than an already-declared benchmark dataset."
    },
    {
      "workflow_id": "generic-tabular-benchmark",
      "score": 0.22,
      "reason": "The request does not primarily ask for direct benchmark execution from a known dataset."
    }
  ]
}
```

## Who Owns The Decision

The ranker should not create or approve runs.

`workflow-api` should remain the owner of:

- candidate generation
- thresholding
- fallback behavior
- persistence of the final chosen workflow family

That keeps the ranker advisory even when it is useful.

## Failure Rules

Fail closed if:

- the top score is below threshold
- the top two scores are too close
- the returned candidate IDs do not match the offered set
- the response shape is malformed

Fallbacks:

- deterministic heuristic choice if it is strong enough
- ask for clarification
- keep the intake record unresolved

## Deployment Shape

The best first deployment target is a separate Mac-hosted service, not a Kubernetes Deployment.

Why:

- it uses the new Apple-silicon capacity without changing the cluster architecture
- it is easy to replace or remove if it disappoints
- it does not widen trust inside the cluster

Suggested split:

- `192.168.1.23`: heavier primary operator inference host
- `192.168.1.12`: smaller secondary inference or ranker host

## Live Validation

Validated on `2026-03-24`:

- `192.168.1.12` is now serving `qwen3:14b` via Ollama on `:11434`
- a bounded ranker wrapper is running on `:8181`
- `GET /healthz` returns `200`
- `POST /rank/workflow-family` returns ranked candidates for the repo request shape

Implementation note:

- the canonical repo service remains the FastAPI app in `services/ranker/app/`
- the current live host wrapper is `services/ranker/live_server.rb`
- that Ruby wrapper exists only because the Mac host did not yet have usable Python CLI tooling from the shell

## API Boundary

The ranker service should expose one tiny internal API.

Example:

- `POST /rank/workflow-family`

This is enough to test the value of ranking without prematurely building a larger agent service.

## What Not To Do First

Do not first make the ranker:

- choose tools
- call backend APIs directly
- approve workflows
- synthesize run manifests
- act as a hidden orchestration brain

Those are exactly the parts Glasslab is already moving away from.

## Practical Near-Term Sequence

1. define the request and response schema
2. have `workflow-api` generate bounded candidate sets
3. call the ranker only for advisory ranking
4. store the result as part of intake resolution
5. compare ranker-assisted routing against deterministic-only routing before widening use
