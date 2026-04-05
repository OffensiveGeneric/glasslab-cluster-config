# WhatsApp Gateway

`whatsapp-gateway` is the first repo-owned replacement for OpenClaw on the
critical command/control path.

Its job is intentionally narrow:

- accept inbound WhatsApp-shaped messages
- persist a minimal session/message log
- merge PDF attachment URLs into `!add-pdf` when appropriate
- forward deterministic commands to `research-ingress`
- return the backend `response_text` directly

It does **not** currently:

- provide free-form chat
- call an LLM
- perform tool orchestration
- own workflow logic

Current contract:

- `GET /healthz`
- `POST /webhooks/whatsapp/inbound`
- `POST /webhooks/whatsapp/provider`
- `GET /sessions/{channel}/{sender}`

The first slice is a bounded control-plane replacement, not a full chat shell.

Provider-facing notes:

- `POST /webhooks/whatsapp/provider` is the provider-oriented entrypoint for
  WhatsApp-style webhook events.
- provider retries can be suppressed by stable `provider_message_id`, so the
  gateway can absorb duplicate delivery events without re-forwarding the same
  PDF add or command turn to the backend.
