# Research Ingress

`research-ingress` is the repo-owned ingress layer for Glasslab research traffic.

It is intentionally distinct from OpenClaw:

- `research-command-router` owns deterministic command handling
- `research-ingress` owns inbound message routing
- OpenClaw remains the free-form conversational backend

Current contract:

- `POST /inbound`
- request:
  - `message`
  - `sender`
  - `channel`
- response:
  - `handled`
  - `route`
  - `response_text`
  - `forward_to_openclaw`
  - `router_payload`

Current behavior:

- explicit research commands are handled deterministically through
  `research-command-router`
- non-command turns are marked for OpenClaw fallback

Important current boundary:

- this service does **not** yet directly forward non-command turns into OpenClaw
- that bridge is separate because the current validated OpenClaw CLI surface does
  not support programmatic WhatsApp message reads, and the gateway RPC contract
  still needs a stable repo-owned adapter for free-form turns

Why this still matters:

- it gives Glasslab a repo-owned ingress contract now
- it separates inbound routing from model behavior
- it lets future WhatsApp or web entrypoints target one narrow service instead
  of talking directly to OpenClaw
