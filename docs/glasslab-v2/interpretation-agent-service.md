# Interpretation Agent Service

This note defines the first bounded in-cluster stage agent that should be built next.

The goal is not to create a new general orchestrator.

The goal is to add one narrow backend service that helps `workflow-api` produce better interpretation records from intake records.

## Purpose

The interpretation agent should do one job:

- turn an intake record into an `InterpretationRecord`-shaped draft

It should not:

- approve execution
- create runs directly
- mutate cluster state
- choose infrastructure settings

## Why This Agent First

This is the best first stage agent because:

- `workflow-api` already has `InterpretationRecord`
- the current deterministic interpretation path is intentionally simple
- the task benefits from stronger model reasoning
- bad output can still fail into review instead of causing execution

## Ownership Boundary

### `workflow-api` remains the owner of:

- intake persistence
- invoking the interpretation service
- schema validation of the returned payload
- fallback to deterministic interpretation if the service fails
- persistence of the final interpretation record
- all later transitions into assessment, design, and run creation

### interpretation-agent owns:

- model prompt shaping for interpretation
- calling the selected inference backend
- returning a bounded structured draft

## Suggested API

### `POST /interpret-intake`

Request shape:

```json
{
  "request_id": "intake-123",
  "intake": {
    "intake_id": "intake-123",
    "source_type": "paper-link",
    "source_refs": ["https://example.org/paper"],
    "document_refs": ["doc-abc123"],
    "raw_request": "Read this paper and propose a bounded reproduction path.",
    "normalized_summary": "Paper-derived reproduction request.",
    "workflow_family_candidates": [
      "literature-to-experiment",
      "replication-lite"
    ],
    "notes": [
      "Prefer approved workflow families only."
    ],
    "submitted_by": "glasslab-operator"
  }
}
```

Response shape:

```json
{
  "request_id": "intake-123",
  "draft": {
    "source_type": "paper-link",
    "normalized_summary": "Paper-derived reproduction request.",
    "extracted_method_summary": "The paper appears to describe ...",
    "candidate_workflow_families": [
      "replication-lite",
      "literature-to-experiment"
    ],
    "dataset_hints": [
      "titanic"
    ],
    "evaluation_targets": [
      "classification accuracy"
    ],
    "extracted_claims": [
      "The method claims improved survival prediction performance."
    ],
    "unresolved_questions": [
      "Which exact evaluation split should be treated as canonical?"
    ]
  },
  "model_backend": {
    "provider": "openai-compatible",
    "base_url": "http://192.168.1.21:52415",
    "model": "mlx-community/Qwen3-Coder-Next-4bit"
  }
}
```

## Validation Rules

The service response should be rejected by `workflow-api` unless:

- `candidate_workflow_families` is a subset of approved workflow IDs already present in the intake candidate set or registry
- all list fields are unique and non-empty after normalization
- the response shape is complete and schema-valid
- no execution-control fields appear

If validation fails:

- log the failure
- fall back to the deterministic builder
- keep the stage reviewable

## Deployment Shape

This service should run **inside Kubernetes**.

Suggested first shape:

- namespace: `glasslab-v2`
- deployment: `glasslab-interpretation-agent`
- service: `glasslab-interpretation-agent`
- service type: `ClusterIP`

The agent service should not store durable state.

## Inference Dependency

The service should call external Mac-hosted inference, not host the model itself in the first pass.

Current canonical backend:

1. `.21` exo OpenAI-compatible endpoint
2. model: `mlx-community/Qwen3-Coder-Next-4bit`
3. deterministic scaffold fallback inside the service if the model lane fails

This keeps:

- one bounded model-serving lane for stage agents
- bounded backend logic in-cluster
- cluster GPU free for later experiments

When `document_refs` are available, `workflow-api` should hydrate stored
document excerpts and pass them into the interpretation input so the agent can
reason about fetched paper content, not only URLs and operator notes.

## Suggested Environment Variables

For the interpretation-agent service:

- `GLASSLAB_INTERPRETATION_AGENT_PROVIDER_BASE_URL`
- `GLASSLAB_INTERPRETATION_AGENT_PROVIDER_API`
- `GLASSLAB_INTERPRETATION_AGENT_MODEL`
- `GLASSLAB_INTERPRETATION_AGENT_TIMEOUT_SECONDS`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_PROVIDER_BASE_URL`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_PROVIDER_API`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_MODEL`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_TIMEOUT_SECONDS`

For `workflow-api`:

- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_TIMEOUT_SECONDS`

## Integration Pattern In `workflow-api`

Recommended behavior for `POST /interpretations/from-latest-intake`:

1. load latest intake
2. if interpretation-agent integration is disabled:
   - use the current deterministic builder
3. if enabled:
   - call `POST /interpret-intake`
   - validate the returned draft
   - on success, build and persist the final `InterpretationRecord`
   - on failure, log and fall back to deterministic interpretation

That means the existing endpoint contract does not have to change.

## Scheduling / Placement

Do not pin the first version to `node02`.

The service itself can run on any worker because the inference work is remote on the Macs.

Only revisit node pinning if:

- locality matters
- a later in-cluster model-serving path is introduced
- the service grows CPU or memory demands that justify explicit placement

## Non-Goals

Do not add in the first pass:

- autonomous assessment chaining
- hidden retries that mutate records multiple times
- direct calls from OpenClaw to the interpretation service
- free-form run planning
- side effects outside the interpretation draft

## Success Criteria

The first pass is successful if:

1. the service runs in-cluster
2. `workflow-api` can call it optionally
3. bad outputs fail closed into deterministic fallback
4. the interpretation quality is measurably better than the deterministic baseline on real intake examples
