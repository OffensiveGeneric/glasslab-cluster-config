# Chat Ingress And OpenClaw Boundary

This note captures the current product stance after the repeated OpenClaw
tool-calling and orchestration failures.

The goal is still a research assistant that you can talk to through a chat app.
What changed is the control boundary:

- the chat surface should remain unified for the user
- the deterministic action path should be owned by repo code
- OpenClaw should no longer be the only ingress or the workflow planner

## What We Still Want

The intended user experience is still:

- use one chat interface such as WhatsApp
- talk naturally about a research idea
- trigger concrete backend actions from that same interface
- review papers, notes, and experiments in the same conversation
- later let the system automate more of the loop

So this is **not** a move away from chat as the front door.
It is a move away from letting the LLM own the whole front door.

## Current Boundary

The platform should now be thought of in four layers.

### 1. Chat Interface

Examples:

- WhatsApp
- later a small web UI or operator console

This layer should feel unified to the user.
It does not need to expose the internal split between deterministic commands and
free-form conversation.

### 2. Repo-Owned Ingress

Current services:

- [research-ingress](./research-ingress.md)
- [research-command-router](./research-command-router.md)

This layer owns:

- inbound message routing
- deterministic command handling
- direct calls to `workflow-api`
- explicit "forward to OpenClaw" decisions for non-command turns

This is the critical shift.
Ingress semantics now live in repo code rather than in OpenClaw prompt luck.

### 3. OpenClaw

OpenClaw still has a role, but it is now narrower:

- conversation
- explanation
- synthesis
- free-form discussion
- non-command fallback

OpenClaw should **not** be relied on for:

- deciding whether an obvious command should hit the backend
- multi-step orchestration of the core research loop
- classifying backend failures on its own

### 4. `workflow-api`

`workflow-api` remains the system of record for:

- sessions
- research problems
- paper queues
- source documents
- intake
- interpretation
- assessment
- design
- runs
- operations

This is where the real research loop lives.

## The Current Product Stance

The current intended product is:

- one user-facing chat surface
- one repo-owned ingress layer
- deterministic research commands where reliability matters
- OpenClaw for free-form conversation
- backend-owned research work and state

Short version:

- same chat interface
- different responsibility split

## Why This Is The Right Order

We do **not** need full automation first.

We need, in order:

1. a backend that can run the research loop
2. a reliable way to trigger that loop from chat
3. enough persistent state to discuss the work over time
4. only later, more automation and agentic behavior

So the next milestone is not "make the system autonomous."
The next milestone is "make the same chat interface reliably trigger the work we
actually care about."

That means:

- command-mode and deterministic ingress first
- experiment execution substrate first
- automation later

## What This Means For Automation

Agentic behavior is still part of the vision, but it should come later and sit
on top of a stable substrate.

Later automation should help with:

- literature comparison
- methodological differences
- bounded next-experiment proposals
- comparison of alternate losses, baselines, augmentations, and evaluation
  schemes
- deciding what to try next from prior runs

But the system should first be able to do those things in a controlled,
human-triggered way.

## Concrete Near-Term Direction

The near-term path is:

1. keep the same chat-facing interface concept
2. front it with `research-ingress`
3. route deterministic commands to `research-command-router`
4. send only non-command turns to OpenClaw
5. keep extending the backend research loop:
   - better literature search
   - source-document storage
   - interpretation
   - assessment
   - design
   - `gpu-experiment`

Success looks like:

- the user can stay in one chat interface
- the backend commands actually work
- OpenClaw is helpful when conversation matters
- the system can later automate from a position of strength instead of prompt luck

## Explicit Non-Goals Right Now

Not the current priority:

- making OpenClaw the sole ingress again
- relying on prompt engineering to recover critical actions
- building fully autonomous research agents before the execution substrate is solid
- debating complete automation before the manual/semi-manual loop is reliable

## Summary

The platform is not moving away from chat.
It is moving away from LLM-owned ingress.

The right target is:

- chat interface for the human
- repo-owned ingress for reliability
- OpenClaw for conversation
- backend contracts for research work
- automation after the loop is real
