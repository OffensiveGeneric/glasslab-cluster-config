# Interpretation Agent

`interpretation-agent` is the first bounded stage-agent service for Glasslab v2.

It accepts one intake-shaped request and returns one bounded interpretation draft.

It does not:

- approve execution
- create runs
- mutate Kubernetes state
- own durable workflow state

The intended caller is `workflow-api`, not OpenClaw directly.

## Current Scope

Current implementation is a bounded Ollama-backed service:

- `GET /healthz`
- `POST /interpret-intake`
- primary bounded interpretation against `.23` `qwen3:30b`
- fallback bounded interpretation against `.12` `qwen3:14b`
- deterministic bounded draft fallback if both backends fail
- accepts `document_refs` from `workflow-api` so stored source-document context
  can be threaded into model-backed interpretation
- response metadata that records the configured model backend

This keeps the stage bounded and reviewable while allowing stronger model-backed
interpretation where available.

## Intended Deployment Shape

- namespace: `glasslab-v2`
- deployment: `glasslab-interpretation-agent`
- service: `glasslab-interpretation-agent`
- service type: `ClusterIP`

## Environment

- `GLASSLAB_INTERPRETATION_AGENT_PROVIDER_API`
- `GLASSLAB_INTERPRETATION_AGENT_PROVIDER_BASE_URL`
- `GLASSLAB_INTERPRETATION_AGENT_MODEL`
- `GLASSLAB_INTERPRETATION_AGENT_TIMEOUT_SECONDS`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_PROVIDER_API`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_PROVIDER_BASE_URL`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_MODEL`
- `GLASSLAB_INTERPRETATION_AGENT_FALLBACK_TIMEOUT_SECONDS`

## Example

```bash
uvicorn app.main:app --reload --port 8091
```

```bash
curl -s http://127.0.0.1:8091/healthz
curl -s \
  -H 'content-type: application/json' \
  -d '{
    "request_id": "intake-1",
    "intake": {
      "intake_id": "intake-1",
      "source_type": "paper-link",
      "source_refs": ["https://example.org/paper"],
      "raw_request": "Read this paper and propose a bounded reproduction path.",
      "normalized_summary": "Paper-derived reproduction request.",
      "workflow_family_candidates": ["literature-to-experiment", "replication-lite"],
      "notes": ["Prefer approved workflow families only."],
      "submitted_by": "glasslab-operator"
    }
  }' \
  http://127.0.0.1:8091/interpret-intake
```
