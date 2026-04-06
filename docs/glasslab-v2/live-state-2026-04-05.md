# Live State 2026-04-05

## Summary

The first Glasslab-owned WhatsApp/control shell is now live in the cluster.

This is the first slice of replacing OpenClaw on the critical command/control
path with a repo-owned service.

## Live Service

- service: `glasslab-whatsapp-gateway`
- namespace: `glasslab-v2`
- deployment image:
  - `ghcr.io/offensivegeneric/glasslab-whatsapp-gateway:0.1.2-local`
- current node:
  - `node05`

## What Was Validated

### 1. Health

`GET /healthz` responds cleanly and reports:

- `research_ingress_url`
- `state_dir`
- timeout budget

### 2. Deterministic Command Forwarding

A live `!status` turn through the gateway succeeded and returned backend-owned
state directly.

Observed response characteristics:

- `handled: true`
- `route: deterministic-router`
- `forwarded_message: "!status"`
- user-facing `response_text` came from the deterministic backend path

That proves the primary architecture point:

- WhatsApp-shaped inbound message
- `whatsapp-gateway`
- `research-ingress`
- `research-command-router`
- `workflow-api`

without OpenClaw on the command path.

### 3. Session Transcript Ownership

The gateway now persists its own per-sender transcript and can return it through:

- `GET /sessions/{channel}/{sender}`

Validated contents included:

- user turns
- assistant turns
- attached PDF metadata
- deterministic route/handled markers on assistant replies

### 4. Attachment-Aware PDF Path

PDF-shaped inbound turns are reaching the deterministic backend path and result
in manual PDF candidates being added to the current queue.

The live transcript clearly showed assistant responses of the form:

- `Added PDF candidate 'Manual PDF candidate' to the current queue.`

and a later `!status` confirmed the queue candidate count increased.

## Current Boundary

What the gateway does now:

- receives WhatsApp-shaped inbound messages
- stores minimal transcript state
- converts PDF uploads into `!add-pdf` behavior when appropriate
- accepts provider-facing WhatsApp webhook events through
  `POST /webhooks/whatsapp/provider`
- exposes a Meta WhatsApp Cloud API-style provider adapter through:
  - `GET /webhooks/meta/whatsapp`
  - `POST /webhooks/meta/whatsapp`
- can proxy Meta media objects through:
  - `GET /attachments/meta/{media_id}`
- forwards deterministic commands directly to `research-ingress`
- can optionally answer non-command turns through a configured Ollama-style chat
  backend
- can enforce sender allowlists and separate group-chat policy before allowing
  that chat path
- returns backend `response_text` directly

What it does not do yet:

- replace every remaining OpenClaw-related operational path
- provide proven true group-chat support on a real external WhatsApp provider

## Provider Adapter Follow-On

The next gateway slice after sender-pinned sessions adds a real provider-aware
surface for Meta WhatsApp Cloud API-style delivery:

- webhook verification via `GET /webhooks/meta/whatsapp`
- inbound normalization from provider payloads into the same deterministic
  gateway path used by the internal webhook tests
- document/media proxying so provider-hosted PDFs can become backend-fetchable
  `!add-pdf` targets without requiring a pasted public URL
- optional outbound reply dispatch when Meta credentials are configured

This narrows the remaining gap between the current cluster-side gateway and the
actual external WhatsApp front door.

Live validation on `.44` confirmed:

- `GET /webhooks/meta/whatsapp` is present on the running gateway
- when no verify token is configured, it fails explicitly with:
  - `503 meta verify token is not configured`
- `GET /attachments/meta/{media_id}` is present on the running gateway
- when no Meta access token is configured, it fails explicitly with:
  - `503 meta access token is not configured`
- `POST /webhooks/meta/whatsapp` now accepts real Meta-style payloads and
  normalizes them into the deterministic command path

Validated live examples:

- a Meta text payload with `!help` returned:
  - `provider: "meta-whatsapp"`
  - `processed_messages: 1`
  - `forwarded_message: "!help"`
  - `route: "deterministic-router"`
- a Meta document payload with a PDF attachment returned:
  - `forwarded_message: "!add-pdf http://glasslab-whatsapp-gateway.glasslab-v2.svc.cluster.local:8097/attachments/meta/meta-doc-2"`
  - proving the gateway can turn a provider-hosted document into a
    backend-fetchable PDF target without requiring a manually pasted public URL

## Follow-On Fix

The first live slice exposed a real duplicate-add problem for repeated PDF
retries.

That is now fixed in the gateway layer.

Validated behavior after the follow-on fix:

- the first PDF-style turn forwards to the deterministic backend and adds the
  manual PDF candidate
- the second identical PDF-style turn returns the same user-facing response
  without forwarding again
- the response now carries:
  - `router_payload: {"duplicate_suppressed": true}`
- the transcript stays clean:
  - no second duplicate user/assistant pair
- the queue does not gain an extra duplicate candidate from the retried turn

This fix is intentionally gateway-local:

- no workflow-api change was required
- no OpenClaw behavior is involved
- the command/control shell now owns a basic idempotency boundary itself

## Provider Webhook Dedupe

The gateway now also supports a provider-oriented WhatsApp webhook shape:

- `POST /webhooks/whatsapp/provider`

Live validation on `.44` confirmed:

- a provider event with a new `provider_message_id` is processed normally
- a PDF-style provider event with a new `provider_message_id` adds the manual
  PDF candidate normally
- a repeated provider retry with the same `provider_message_id` is suppressed
  before a second backend forward

Observed response characteristics for the repeated provider retry:

- `router_payload.duplicate_suppressed: true`
- `router_payload.duplicate_scope: "provider_message_id"`
- `router_payload.provider_message_id` echoed the retried provider ID

The transcript for the validated sender showed only one user turn and one
assistant reply for the PDF add tied to that provider message ID, proving the
gateway absorbed the duplicate delivery event locally.

## Why This Still Matters

Even with the duplicate caveat, this is already a better direction than the old
OpenClaw command path because:

- the deterministic command/control path is now ours
- session transcripts are now ours
- attachment handling is now ours
- OpenClaw is no longer required for the critical runner loop

## Provisioner Reconciliation

The `.44` provisioner checkout was reconciled after the gateway work:

- `/home/glasslab/cluster-config` is clean again at the current GitHub-backed
  state
- the old dirty tree is preserved at:
  - `/home/glasslab/cluster-config-prev`
- an explicit preservation branch and handoff snapshot were written on `.44`

The scary-looking `.44` conflict turned out not to hide major unpublished API
progress:

- most tracked files in the old tree were already byte-for-byte identical to
  the current GitHub-backed checkout
- the remaining genuine tracked diffs were older content, not newer runner or
  workflow logic

## Helper Reliability

The local gateway helper path is also stronger now:

- `whatsapp-gateway-cli.sh` no longer assumes one fixed local port for every
  port-forward
- it now chooses a free local port automatically when needed
- it waits for a real `/healthz` response instead of only checking for an open
  socket
- `whatsapp-gateway-remote.sh` now invokes the remote helper through `bash`
  directly instead of assuming the execute bit is present

## Sender-Pinned Sessions

The control shell is now stronger in one important way:

- the gateway persists the last workflow `session_id` it learned for each
  sender transcript
- `research-ingress` and `research-command-router` now accept an optional
  `session_id`
- deterministic commands can be scoped to that pinned workflow session instead
  of always falling through the backend's global `latest` alias

Live sequential validation on `.44` confirmed:

1. a provider webhook `!new-session artist similarity session pinning test`
   created a fresh workflow session for sender `+15555550987`
2. the next provider webhook `!status` for the same sender hit:
   - `/research-sessions/{session_id}/context`
   - not `/research-sessions/latest/context`
3. the gateway transcript for that sender stored the pinned
   `workflow_session_id` on the assistant and subsequent user message records

That means the repo-owned WhatsApp gateway is no longer just a thin text proxy.
It now carries enough sender-local state to keep deterministic commands pointed
at the right backend session.
