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
- `GET /sessions/{channel}/{sender}`

The first slice is a bounded control-plane replacement, not a full chat shell.
