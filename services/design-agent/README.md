# Design Agent

`design-agent` is the bounded stage-agent for turning an intake plus approved
workflow choice into a reviewable design draft.

It accepts one design-request payload and returns one bounded `DesignDraft`-style
draft.

It does not:

- submit runs
- choose cluster placement
- bypass the workflow registry
- approve unresolved execution-critical inputs

The intended caller is `workflow-api`.

## Current Scope

Current implementation is a scaffold:

- `GET /healthz`
- `POST /draft-design`
- deterministic draft construction
- response metadata describing the configured model backend

This keeps the service boundary concrete before any live model-backed draft
generation is enabled.
