# Live State 2026-03-31

This note captures the additional in-lab validation completed on 2026-03-31.

## What Changed Live

- `workflow-api` was rolled with the session-bootstrap fix from:
  - `f38719a` `Harden research session bootstrap flow`
- `workflow-api` was rolled again with session-alias hardening from:
  - `7605955` `Harden latest session workflow-api aliases`
- `research-command-router` was rolled with the timeout increase from:
  - `7bff91a` `Raise research command router timeouts`

## What Was Proved Live

### Fresh `!research` goals now create fresh sessions

This was the main command-path fix from this pass.

Validated through the deterministic ingress on `.44`:

- `!research replicate DreamSim visual similarity metric`
- `!research vision-transformer image forgery detection with pytorch and timm`

Both now returned:

- `action: created-session-from-new-goal; staged-research-problem; started-literature-harvest`

and each produced its own distinct `session_id`.

That means the earlier bug is closed:

- a new `!research` goal no longer silently reuses the previous active session

### `!next-paper` now completes through the deterministic router

The router timeout was previously too short for source fetch / intake work.

After raising the router timeout to `120s` and rolling `glasslab-research-command-router:0.1.2`,
the same live path returned a clean response instead of disconnecting:

- `!next-paper`

returned a staged intake with:

- `status: ready_for_design`
- a real `document_ref`
- a session-bound `intake_id`

So the paper staging path is now materially smoother.

### Session context reflects the staged paper and interpretation

Live `!session` after `!next-paper` showed:

- `latest_document_id`
- `latest_intake_id`
- `latest_interpretation_id`

The attached source document and interpretation were visible in session context.

### `!interpret` is now clean through the helper, but materially slower than the other commands

The important backend fact:

- an interpretation record was successfully created and attached to the session

The important operator fact:

- the command completes end to end through the deterministic ingress path
- direct validation on `.44` showed the full round-trip took about `66.8s`
- a fresh validation later in the same pass returned cleanly again with:
  - `Created interpretation '<id>'. Preferred workflow: literature-to-experiment.`
- that is much slower than `!design` and `!preflight`, which both returned in
  under a second on the same session

The created interpretation showed:

- `status: needs_review`
- `candidate_workflow_families: ["literature-to-experiment", "replication-lite"]`
- `preferred_workflow_id: "literature-to-experiment"`
- `preferred_resource_profile: "cpu-medium"`
- interpretation provenance and warnings from the `.23` / `.12` fallback chain

So the backend lane is real, and the helper now returns a clean success response. The remaining work is mostly latency, not correctness of the routed backend action.

### `!design` now completes through the deterministic router

The earlier `404` was a real backend alias bug:

- `POST /research-sessions/latest/skills/design` was being shadowed by the
  dynamic `/{session_id}` route

After hardening the session-scoped handlers to explicitly resolve
`session_id == "latest"`, live `!design` now returns a real design draft.

Validated live through the deterministic ingress helper:

- `!design`

returned:

- `Created design draft '<id>'. Workflow: literature-to-experiment (needs_review).`

and populated `latest_design_id` in session context.

## `.21` Flash-MoE Status

Additional direct validation on `.21` from the lab:

- bootstrap remains complete
- CLI `./infer` still runs and produces output
- server mode still exposes:
  - `GET /health`
  - `GET /v1/models`

The HTTP completion contract is improved but the runtime is still not usable.

What is now fixed:

- `stream: false` requests return a single JSON completion response instead of
  SSE chunks
- `vocab.bin` now includes the added-token range used by Qwen chat formatting,
  so the runtime no longer collapses those generated ids into `<unk>`
- the `.21` `flash-moe` binary now points at the real local snapshot under
  `/Users/glasslab/...` instead of the stale upstream author path, so it sees
  `60/60` packed expert layer files instead of `0/60`

What was fixed in a later `.21` debug pass:

- the serve-mode response path now strips leading `<think>` / `</think>` remnants
  from the final non-stream JSON response
- a fresh rebuilt server on port `8001` returned a non-empty bounded answer:
  - `A transformer is a type of deep learning model that relies entirely on a self-attention mechanism to process sequential data, enabling it to learn complex`
- a later sampler fix improved first-token behavior further, and a three-prompt
  probe on `8001` showed:
  - coherent:
    - transformer
    - PyTorch
  - still noisy:
    - DreamSim

What is still bad:

- sample outputs remain unstable or malformed, including:
  - `Yes`
  - `$$`
  - `1`
- the runtime still generates very short, low-quality completions on trivial prompts
- request parsing and content quality remain fragile
- completion quality is better than the earlier empty/`</` responses, but still
  not good enough to treat `.21` as a Glasslab backend
- a stronger plain-text system prompt and a more aggressive special-token
  suppression patch both made quality worse, so the current best state is the
  lighter-touch sampler and the shorter default system prompt

So `.21` is still:

- a live experimental inference runtime

and still not:

- a backend we should route Glasslab traffic to

## Practical Command-State Summary

Current deterministic ingress quality:

- good:
  - `!help`
  - `!research`
  - `!session`
  - `!next-paper`
  - `!design`
  - `!preflight`
  - `!start-autoresearch`
  - `!draft-methodologies`
  - `!autoresearch`
  - `!model-comparison`
  - `!draft-notebook`
  - `!refine-notebook`
  - `!launch-iteration`
  - `!decide-latest`
- slower but working:
  - `!interpret`

Fresh end-to-end command checks on `.44` also reconfirmed:

- `!run` reaches the backend and fails for the correct state reason:
  - `design draft is not ready_for_run`
- `!autoresearch`, `!model-comparison`, `!draft-notebook`, and
  `!refine-notebook` all return cleanly through `deterministic-router`

As of the latest 2026-03-31 validation:

- `literature-to-experiment` now explicitly declares the optional
  `validation_strategy` and `validation_split` inputs expected by the bounded
  autoresearch lane
- `!launch-iteration` now reaches the backend, creates a validation run, and
  submits the Kubernetes Job successfully
- `!decide-latest` now records a durable decision after launch; in the latest
  smoke pass it stored `escalate_for_review`
- `!model-comparison` now surfaces a real compared candidate and recommends the
  current best model for the campaign

The key stabilization for the expanded autoresearch command set was:

- `research-command-router` now resolves the active session id from
  `/research-sessions/latest/context`
- it then calls the session-scoped autoresearch endpoints directly instead of
  relying on the more brittle backend `latest` aliases
- this keeps the command path deterministic without expanding OpenClaw
  discretion

## Next Concrete Fixes

1. reduce `!interpret` latency or move it onto an inspectable operation record so the chat/admin path is not waiting synchronously for ~67s
2. keep `.21` off the Glasslab critical path until content quality is substantially better, even though the non-stream API contract is now fixed
3. tighten the end-to-end research flow around better paper relevance for real replication topics like DreamSim
