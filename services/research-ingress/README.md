# Research Ingress

`research-ingress` is the repo-owned front door for Glasslab research traffic.

Its job is intentionally narrow:

- accept inbound messages from a chat or UI channel
- send explicit research commands to `research-command-router`
- return deterministic user-facing text for those commands
- return deterministic rejection text for unsupported or non-command turns

This keeps cluster ingress under repo control and avoids any conversational
fallback dependency.

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
    - `router_payload`
