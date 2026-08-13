# OpenClaw De-Prioritization And Custom WhatsApp Plan

## Decision

OpenClaw should no longer be treated as critical-path infrastructure for the
bounded experiment runner.

It may still remain useful later as:

- an optional conversational shell
- a result-explanation surface
- a place to explore broader agent UX once the runner is already useful

But for the near-term product, it is getting in the way more than it is helping.

## Why

What the recent work proved:

- `workflow-api` is now the most reliable part of the stack
- `research-ingress` and `research-command-router` are more reliable than the
  chat shell
- the bounded runner path is becoming real
- the main UX pain is now the OpenClaw layer in front of that backend

What OpenClaw is costing us right now:

- extra latency on every command turn
- a two-pass model loop for actions that should be deterministic
- routing ambiguity
- session weirdness
- additional deployment/runtime/export complexity
- more debugging categories than product value

This is the wrong place to spend effort while the main product goal is still:

- get real experiments running
- compare bounded methodology variants
- make the system useful while we are away

## New Product Boundary

The primary operator/control path should become:

1. WhatsApp ingress we own
2. `research-ingress`
3. `research-command-router`
4. `workflow-api`
5. runner / evaluator / reporter

The optional conversational path should become:

1. custom WhatsApp ingress receives the message
2. if it is a deterministic command or attachment action, do not involve an LLM
3. if it is a conversational query, send it to a separate bounded chat service

Short version:

- command/control path: ours
- experiment backend: ours
- conversation: optional and secondary

## What This Means

### Keep

- `workflow-api`
- `workflow-registry`
- `runner`
- `evaluator`
- `reporter`
- `research-ingress`
- `research-command-router`

### De-Prioritize

- OpenClaw as the primary operator front door
- OpenClaw as the WhatsApp command surface
- OpenClaw-specific routing fixes as top-priority work
- OpenClaw-specific prompt tuning as a latency/reliability strategy

### Preserve But Downgrade

- `services/openclaw-config/`
- existing OpenClaw manifests and runbooks
- prior docs about OpenClaw boundaries and tool-calling reliability

These should remain as historical context and optional future work, not the main
product path.

## Immediate Migration Plan

### Phase 1: Replace OpenClaw On The Critical Path

Build a Glasslab-owned WhatsApp gateway that:

- receives WhatsApp messages and attachments
- detects deterministic command turns directly
- sends those turns to `research-ingress`
- returns `response_text` directly to the user
- never asks an LLM to interpret `!commands`

First supported actions:

- `!new-session <goal>`
- `!add-pdf [url]`
- `!start <goal>`
- `!run`
- `!next`
- `!compare`
- `!status`

Attachment support should include:

- PDF upload detection
- association with the active session
- handoff into source-document / manual-paper intake

### Phase 2: Add A Separate Chat Lane

Only after the direct command path is stable:

- add a bounded chat endpoint for:
  - interpreting results
  - explaining comparisons
  - discussing next experiments
  - drafting technique cards or notes

This chat lane should not own:

- command dispatch
- run creation
- session bootstrap
- intake staging
- experiment sequencing

### Phase 3: Revisit OpenClaw Later If It Earns Its Keep

Only revisit OpenClaw if we later want:

- richer multi-channel chat UX
- agent/session abstractions that actually save work
- a conversational surface that no longer blocks the runner path

Until then, OpenClaw should be treated as optional.

## Implementation Targets

### New Primary Surface

Add a small repo-owned WhatsApp service with responsibilities:

- provider webhook / inbound message receive
- attachment metadata capture
- sender/session association
- direct call to `research-ingress`
- direct outbound message send
- light audit logging

### Existing Services To Reuse

- `research-ingress` remains the inbound contract
- `research-command-router` remains the deterministic action surface
- `workflow-api` remains the stateful orchestrator

This is intentionally an additive replacement of OpenClaw on the front door, not
a rewrite of the backend.

## Why This Is Better

- fewer moving parts in the critical loop
- less latency
- fewer model round trips
- fewer routing bugs
- less session confusion
- clearer ownership boundary
- easier debugging

Most importantly:

- it puts effort back into the experiment-runner instead of the chat shell

## Done When

- the primary WhatsApp runner flow no longer depends on OpenClaw
- PDF upload and session creation work through the Glasslab-owned ingress path
- `!start`, `!run`, `!next`, `!compare`, and `!status` feel faster and more
  deterministic than the current OpenClaw path
- OpenClaw can be scaled down or ignored without blocking the main product
