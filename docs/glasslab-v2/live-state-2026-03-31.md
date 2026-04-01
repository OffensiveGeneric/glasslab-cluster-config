# Live State 2026-03-31

This note captures the additional in-lab validation completed on 2026-03-31.

## What Changed Live

- `workflow-api` was rolled with the session-bootstrap fix from:
  - `f38719a` `Harden research session bootstrap flow`
- `workflow-api` was rolled again with session-alias hardening from:
  - `7605955` `Harden latest session workflow-api aliases`
- `workflow-api` was rolled again with the bounded runner bridge from:
  - `d6b7d17` `Add bounded method spec for runs`
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

### The bounded runner bridge is live

The important live change from the latest pass is that `workflow-api` now
converts interpretation output into a bounded `MethodSpec`, and the run-launch
path consumes that contract instead of relying on loose design prose.

Validated directly against the live `workflow-api` on `.44`:

- `POST /intakes`
- `POST /interpretations/from-latest-intake`
- `POST /design-drafts/from-latest-intake`
- `POST /runs/from-latest-design-draft`

On the same live pass:

- interpretation returned `method_spec.workflow_id: "generic-tabular-benchmark"`
- interpretation returned `method_spec.run_readiness: "ready"`
- interpretation returned bounded execution inputs including:
  - `train_uri: s3://datasets/paper-derived/train.csv`
  - `test_uri: s3://datasets/paper-derived/test.csv`
  - `validation_strategy: holdout`
  - `validation_split: 0.2`
- design draft returned:
  - `status: ready_for_run`
  - `workflow_id: generic-tabular-benchmark`
  - a carried-forward `method_spec`
- run creation succeeded and produced an accepted run manifest using those
  bounded inputs

The same live validation also proved the bounded autoresearch launch path:

- `POST /research-sessions/{session_id}/transitions/start-autoresearch-campaign`
- `POST /research-sessions/{session_id}/transitions/draft-methodologies`
- `POST /research-sessions/{session_id}/transitions/launch-autoresearch-iteration`

That path now:

- drafts methodology variants that each carry a bounded `method_spec`
- launches a validation run from the selected methodology draft
- submits the Kubernetes Job successfully

Important nuance:

- the session-scoped autoresearch transition path works cleanly
- the raw backend `latest` aliases for those transitions are still weaker than
  the router path
- this is acceptable for the current operator surface because
  `research-command-router` already resolves the active `session_id` first and
  calls the session-scoped endpoints directly

### Provenance caveat

The live rollout is real, but `/healthz` still reports:

- `build_source_revision: 41cf6b6`

even after the `0.1.58-local` rollout. That means the build provenance stamp on
`.44` is stale again even though the live behavior matches the newly rolled
bounded runner code.

## Next Concrete Fixes

1. reduce `!interpret` latency or move it onto an inspectable operation record so the chat/admin path is not waiting synchronously for ~67s
2. make the raw backend `latest` aliases for autoresearch transitions as dependable as the session-scoped path, even though the router already works around that seam
3. keep `.21` off the Glasslab critical path until content quality is substantially better, even though the non-stream API contract is now fixed
4. tighten the end-to-end research flow around better paper relevance for real replication topics like DreamSim
