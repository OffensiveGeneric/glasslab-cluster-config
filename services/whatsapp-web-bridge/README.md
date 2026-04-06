# Glasslab WhatsApp Web Bridge

Small repo-owned transport that connects directly to WhatsApp Web using
Baileys and forwards inbound turns to `glasslab-whatsapp-gateway`.

Purpose:

- remove OpenClaw from the phone-facing path
- keep the existing linked WhatsApp number if the auth state can be migrated
- let `whatsapp-gateway` remain the control/chat shell

The bridge is transport only. It should not contain workflow logic.

Canonical transport contract:

- forward inbound turns to `POST /webhooks/whatsapp/provider`
- send provider-shaped payloads with:
  - `provider`
  - `provider_message_id`
  - `sender`
  - `text`
  - `conversation_id`
  - `is_group`
  - `attachments`
- leave sender normalization, dedupe, session pinning, and policy enforcement
  to `whatsapp-gateway`
