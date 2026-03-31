# Live State 2026-03-31

This note captures the additional in-lab validation completed on 2026-03-31.

## What Changed Live

- `workflow-api` was rolled with the session-bootstrap fix from:
  - `f38719a` `Harden research session bootstrap flow`
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

### `!interpret` is partly working but still rough at the command surface

The important backend fact:

- an interpretation record was successfully created and attached to the session

The important operator fact:

- the current admin helper still surfaced this as an `Internal Server Error`
  instead of a clean success path

The created interpretation showed:

- `status: needs_review`
- `candidate_workflow_families: ["literature-to-experiment", "replication-lite"]`
- `preferred_workflow_id: "literature-to-experiment"`
- `preferred_resource_profile: "cpu-medium"`
- interpretation provenance and warnings from the `.23` / `.12` fallback chain

So the backend lane is real, but the ingress/tooling polish is not done yet.

### `!design` is still not smooth

Live `!design` still returned `404`.

Important nuance:

- the route exists in both local and `.44` source
- but the live service still answered `404 Not Found` for
  `POST /research-sessions/latest/skills/design`

So this remains an active discrepancy between intended route surface and live behavior.

## `.21` Flash-MoE Status

Additional direct validation on `.21` from the lab:

- bootstrap remains complete
- CLI `./infer` still runs and produces output
- server mode still exposes:
  - `GET /health`
  - `GET /v1/models`

But the HTTP completion contract is still not usable:

- `stream: false` responses still come back as SSE chunks
- sample outputs remain unstable or malformed, including:
  - `Yes`
  - `<unk>user`
  - `$$`

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
- mixed:
  - `!interpret`
- still broken or inconsistent:
  - `!design`

## Next Concrete Fixes

1. fix the live `!design` discrepancy so the existing source route is actually usable through the running service
2. clean up ingress/admin helper handling so long-running or mixed-result calls do not look like raw Python failures
3. keep `.21` off the Glasslab critical path until the HTTP server returns proper non-SSE JSON for non-stream requests and substantially better content quality
