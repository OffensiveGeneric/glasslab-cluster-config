# WhatsApp Gateway

`whatsapp-gateway` is the repo-owned command/control edge for WhatsApp.

Its job is intentionally narrow:

- accept inbound WhatsApp-shaped messages
- persist a minimal session/message log
- merge supported attachments into `!add` when appropriate
- forward deterministic commands to `research-ingress`
- return the backend `response_text` directly

It does **not** currently:

- perform tool orchestration
- provide free-form chat fallback
- own workflow logic

Current contract:

- `GET /healthz`
- `POST /webhooks/whatsapp/inbound`
- `POST /webhooks/whatsapp/provider`
- `GET /webhooks/meta/whatsapp`
- `POST /webhooks/meta/whatsapp`
- `GET /attachments/meta/{media_id}`
- `GET /sessions/{channel}/{sender}`

This is a bounded deterministic control surface, not a chat shell.

Provider-facing notes:

- `POST /webhooks/whatsapp/provider` is the provider-oriented entrypoint for
  WhatsApp-style webhook events.
- repo-owned transports like `whatsapp-web-bridge` should target the provider
  entrypoint, not the legacy raw inbound shape.
- `POST /webhooks/whatsapp/inbound` remains available as a legacy/manual test
  seam, not the canonical transport contract.
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

Policy settings:

- `GLASSLAB_WHATSAPP_GATEWAY_DM_POLICY`
- `GLASSLAB_WHATSAPP_GATEWAY_GROUP_POLICY`
- `GLASSLAB_WHATSAPP_GATEWAY_ALLOW_FROM`
- `GLASSLAB_WHATSAPP_GATEWAY_ALLOW_GROUPS`
