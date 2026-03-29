# Research Ingress

`research-ingress` is the repo-owned front door for Glasslab research traffic.

Its job is intentionally narrow:

- accept inbound messages from a chat or UI channel
- send explicit research commands to `research-command-router`
- return deterministic user-facing text for those commands
- mark non-command turns for forwarding to OpenClaw

This keeps cluster ingress under repo control without pretending OpenClaw itself
is a reliable intent router.

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

Important current limitation:

- `research-ingress` does not yet directly invoke OpenClaw for free-form chat
- it returns `forward_to_openclaw=true` for non-command turns
- that is deliberate until the actual OpenClaw bridge contract is made explicit
