# Custom Chat Shell Plan

## Problem

OpenClaw gave us:

- chat transport integration
- session persistence
- model/tool loop machinery

But the part we needed most, reliable backend-aware command mediation, is the
part that has failed most consistently.

The current backend stack is now stronger than the shell in front of it:

- `research-ingress`
- `research-command-router`
- `workflow-api`
- runner / evaluator / reporter

That means the right next step is not more OpenClaw prompt tuning.
It is a Glasslab-owned chat/control shell.

## New Assumption

We still want:

- sessions
- message history
- attachments
- optional model-backed explanation later

We do **not** want:

- model-mediated command dispatch on the critical path
- OpenClaw deciding whether to call backend transitions
- workflow control delegated to a general agent framework

## Architecture

### Deterministic Path

1. WhatsApp webhook or adapter
2. `whatsapp-gateway`
3. `research-ingress`
4. `research-command-router`
5. `workflow-api`

### Optional Conversational Path

Only after the deterministic path is stable:

1. WhatsApp webhook or adapter
2. `whatsapp-gateway`
3. optional bounded chat service
4. read-only access to session/run/comparison state

## First Implementation Slice

The first replacement does only three things:

- persist a minimal session transcript
- merge PDF uploads into `!add-pdf` when appropriate
- forward deterministic commands straight to `research-ingress`

That is enough to remove OpenClaw from the critical command path without
pretending we already have a polished general chat assistant.

Repo service:

- `services/whatsapp-gateway`

Current endpoints:

- `GET /healthz`
- `POST /webhooks/whatsapp/inbound`
- `GET /sessions/{channel}/{sender}`

## What Comes Next

### Phase 1

- run the primary operator loop through `whatsapp-gateway`
- validate PDF upload handling
- keep OpenClaw out of command turns

### Phase 2

- add a real provider adapter for the live WhatsApp backend
- replace remaining OpenClaw-specific command documentation
- make `!start`, `!run`, `!next`, `!compare`, and `!status` the main user path

### Phase 3

- add optional bounded chat for:
  - explaining comparisons
  - interpreting run results
  - discussing next experiments

That chat layer should stay outside execution control.

## Why This Is Better

- fewer moving parts
- lower latency
- clearer ownership
- easier debugging
- attachment handling under repo control
- command flow that matches the current backend reality

## Done When

- the main WhatsApp experiment-runner flow no longer depends on OpenClaw
- session and attachment handling are under repo control
- conversational help, if reintroduced, is optional and secondary
