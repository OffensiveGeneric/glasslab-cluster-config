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
- forwards deterministic commands directly to `research-ingress`
- returns backend `response_text` directly

What it does not do yet:

- integrate with the live external WhatsApp provider directly
- provide free-form chat
- call an LLM
- replace every remaining OpenClaw-related operational path

## Important Caveat

The PDF path is not yet idempotent enough.

What the live validation showed:

- repeated or retried PDF-style turns can add duplicate manual PDF candidates to
  the active queue
- the transcript can also record repeated assistant responses for those retries

So the first gateway slice is already good enough to prove the architecture, but
it still needs:

- message dedupe / idempotency
- attachment dedupe
- queue-side duplicate suppression for identical manual PDF adds

## Why This Still Matters

Even with the duplicate caveat, this is already a better direction than the old
OpenClaw command path because:

- the deterministic command/control path is now ours
- session transcripts are now ours
- attachment handling is now ours
- OpenClaw is no longer required for the critical runner loop
