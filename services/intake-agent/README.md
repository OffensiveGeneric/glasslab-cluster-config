# Intake Agent

`intake-agent` is a bounded stage-agent that normalizes raw intake requests before
later interpretation and design work.

Its job is narrow:

- accept one intake-create-style request
- return one bounded normalized intake draft
- preserve the explicit workflow candidate boundary

It does not:

- approve execution
- create runs
- interpret experimental claims
- mutate durable workflow state directly

The intended caller is `workflow-api`.

## Current Scope

Current implementation is a scaffold:

- `GET /healthz`
- `POST /normalize-intake`
- deterministic normalization logic
- response metadata describing the configured model backend

This is enough to make the service boundary real and testable before live model
integration is added.

## Intended Deployment Shape

- namespace: `glasslab-v2`
- deployment: `glasslab-intake-agent`
- service: `glasslab-intake-agent`
- service type: `ClusterIP`

## Environment

- `GLASSLAB_INTAKE_AGENT_PROVIDER_API`
- `GLASSLAB_INTAKE_AGENT_PROVIDER_BASE_URL`
- `GLASSLAB_INTAKE_AGENT_MODEL`
- `GLASSLAB_INTAKE_AGENT_TIMEOUT_SECONDS`
