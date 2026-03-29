# Live State 2026-03-29

This note records the current practical state after wiring command-mode OpenClaw,
external literature queue generation, and manual paper queueing.

## What Is Working

- `workflow-api` is now the real research-loop backend.
- research sessions are durable and session-centered.
- OpenClaw command mode is the first user-facing path that is reliably close to usable.

Current command surface:

- `!research <topic>`
- `!session`
- `!next-paper`
- `!more-papers`
- `!add-paper <url|title>`
- `!note <text>`
- `!op`
- `!help`

Equivalent `prefix:` forms remain supported.

## Backend State

The current backend can now do all of the following:

- create or resume a research session
- stage a research problem
- create a paper-intake queue
- stage the next paper intake
- persist fetched source documents
- append manual paper candidates to the active session queue
- create an external-literature queue for the active session

New backend routes added in this pass:

- `POST /research-sessions/latest/skills/external-literature-search`
- `POST /research-sessions/{session_id}/skills/external-literature-search`
- `POST /research-sessions/latest/paper-intake-queue/manual-paper`
- `POST /research-sessions/{session_id}/paper-intake-queue/manual-paper`

## Storage Contract

Current storage layout remains:

- session and stage metadata:
  - `/mnt/artifacts/workflow-api/state/run-store.json`
- fetched source-document blobs:
  - `/mnt/artifacts/source-documents`
- run artifacts:
  - `/mnt/artifacts/<run_id>/...`

That means papers are no longer just chat references.
They can exist as:

- queue candidates in session state
- fetched source documents on the shared artifacts PVC
- inputs to later interpretation / assessment / design work

## Literature Source Reality

There are now two literature queue-generation paths:

1. `literature-harvest`
- the older bounded seed-manifest path
- still useful as a fallback

2. `external-literature-search`
- new metadata search path
- current providers:
  - OpenAlex
  - arXiv
  - Crossref
- results are written back into the normal session queue structure

This is the first real move away from the seed-manifest-only paper search path.

## OpenClaw Reality

OpenClaw is in a better state, but the boundary is still important.

What is true:

- the live runtime now contains the command-mode dispatcher
- the live runtime contains `!add-paper`
- the live runtime contains the external-literature queue refresh path
- the backend has the matching routes live

What is still weak:

- free-form natural-language research routing is still unreliable
- command mode is materially better than free chat
- WhatsApp validation still sometimes lags behind in-pod or direct-backend validation because the chat seam remains the weakest layer

## Product Lesson

The system is now proving the intended architecture more clearly:

- sessions are the workspace
- backend contracts are the truth
- skills are bounded capabilities
- OpenClaw works best as a shell over deterministic actions

The more the research loop is exposed as:

- explicit command or router intent
- one backend action
- session-backed durable state

the more usable the product becomes.

## Most Important Remaining Gap

The most important remaining usefulness gap is no longer:

- "can OpenClaw touch the backend at all?"

It is:

- "can the assistant find genuinely relevant literature and move it into the session cleanly?"

So the next product priority should be:

- external literature search and lawful fetch quality

not another round of general prompt surgery.
