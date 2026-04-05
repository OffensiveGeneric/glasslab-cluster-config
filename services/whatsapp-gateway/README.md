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
- `GET /webhooks/meta/whatsapp`
- `POST /webhooks/meta/whatsapp`
- `GET /attachments/meta/{media_id}`
- `GET /sessions/{channel}/{sender}`

The first slice is a bounded control-plane replacement, not a full chat shell.

Provider-facing notes:

- `POST /webhooks/whatsapp/provider` is the provider-oriented entrypoint for
  WhatsApp-style webhook events.
- provider retries can be suppressed by stable `provider_message_id`, so the
  gateway can absorb duplicate delivery events without re-forwarding the same
  PDF add or command turn to the backend.
- the first real external-provider slice now also supports Meta WhatsApp Cloud
  API-style webhook verification and inbound message normalization.
- document uploads from Meta webhooks can be turned into backend-fetchable
  gateway URLs under `GET /attachments/meta/{media_id}` so PDF adds do not
  require a pasted public URL.

Optional Meta settings:

- `GLASSLAB_WHATSAPP_GATEWAY_META_VERIFY_TOKEN`
- `GLASSLAB_WHATSAPP_GATEWAY_META_ACCESS_TOKEN`
- `GLASSLAB_WHATSAPP_GATEWAY_META_PHONE_NUMBER_ID`
- `GLASSLAB_WHATSAPP_GATEWAY_META_GRAPH_API_BASE_URL`
- `GLASSLAB_WHATSAPP_GATEWAY_BASE_URL`
