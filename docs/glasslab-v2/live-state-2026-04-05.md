# Live State 2026-04-05

## Summary

The first Glasslab-owned WhatsApp/control shell is now live in the cluster.

This is the first slice of replacing OpenClaw on the critical command/control
path with a repo-owned service.

## Live Service

- service: `glasslab-whatsapp-gateway`
- namespace: `glasslab-v2`
- deployment image:
  - `ghcr.io/offensivegeneric/glasslab-whatsapp-gateway:0.1.1-local`
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
- forwards deterministic commands directly to `research-ingress`
- returns backend `response_text` directly

What it does not do yet:

- integrate with the live external WhatsApp provider directly
- provide free-form chat
- call an LLM
- replace every remaining OpenClaw-related operational path

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
