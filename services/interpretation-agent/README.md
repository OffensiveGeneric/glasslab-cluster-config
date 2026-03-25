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

Current implementation is a scaffold:

- `GET /healthz`
- `POST /interpret-intake`
- deterministic bounded draft generation
- response metadata that records the configured model backend

This is enough to make the service boundary concrete and testable before live model
integration is added.

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
