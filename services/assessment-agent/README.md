# Assessment Agent

`assessment-agent` is the bounded stage-agent for replicability and execution
readiness assessment.

It accepts one interpretation-shaped request and returns one bounded assessment
draft.

It does not:

- create runs
- choose infrastructure placement
- submit Kubernetes Jobs
- override registry constraints

The intended caller is `workflow-api`.

## Current Scope

Current implementation is a scaffold:

- `GET /healthz`
- `POST /assess-interpretation`
- deterministic assessment logic
- response metadata describing the configured model backend

This keeps the service boundary concrete before any live model-backed assessment
logic is enabled.
