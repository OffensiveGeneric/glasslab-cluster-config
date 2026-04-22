# Research Ingress

`research-ingress` is the repo-owned ingress layer for Glasslab research traffic.

It is intentionally distinct from OpenClaw:

- `research-command-router` owns deterministic command handling
- `research-ingress` owns inbound message routing
- OpenClaw remains the free-form conversational backend

Current contract:

- `POST /inbound`
- request:
  - `message`
  - `sender`
  - `channel`
- response:
  - `handled`
  - `route`
  - `response_text`
  - `forward_to_openclaw`
  - `router_payload`

Current behavior:

- explicit research commands are handled deterministically through
  `research-command-router`
- non-command turns are marked for OpenClaw fallback

Deterministic happy-path boundary for the primary runner loop:

- `!start`
- `!status`
- `!run`
- `!next`
- `!compare`

These five commands now execute through:

- `whatsapp-gateway`
- `research-ingress`
- `research-command-router`
- `workflow-api`

without any OpenClaw dependency on the command turn itself.

Important current boundary:

- this service does **not** yet directly forward non-command turns into OpenClaw
- that bridge is separate because the current validated OpenClaw CLI surface does
  not support programmatic WhatsApp message reads, and the gateway RPC contract
  still needs a stable repo-owned adapter for free-form turns

Why this still matters:

- it gives Glasslab a repo-owned ingress contract now
- it separates inbound routing from model behavior
- it lets future WhatsApp or web entrypoints target one narrow service instead
  of talking directly to OpenClaw

Current practical admin path:

- `.44` helper: `scripts/research-ingress-cli.sh`
- laptop wrapper: `scripts/research-ingress-remote.sh`

Examples:

```bash
./scripts/research-ingress-remote.sh healthz
./scripts/research-ingress-remote.sh dispatch "help:"
./scripts/research-ingress-remote.sh dispatch "research: forged art detection with computer vision methods and open datasets"
./scripts/research-ingress-remote.sh dispatch "!add-paper https://arxiv.org/abs/2401.12345"
```

Important deterministic commands currently covered by the repo-owned ingress path:

- `!start <topic>`
- `!status`
- `!run`
- `!next`
- `!compare`
- `!research <topic>`
- `!more-papers`
- `!next-paper`
- `!add-paper <url|title>`
- `!session`
- `!interpret`
- `!design`
- `!preflight`
- `!run`
- `!start-autoresearch`
- `!draft-methodologies`
- `!draft-notebook`
- `!refine-notebook`
- `!launch-iteration`
- `!launch-batch`
- `!decide-batch`
- `!decide-latest`
- `!autoresearch`
- `!model-comparison`
- `!note <text>`
- `!op`
- `!help`

Operational note from the 2026-03-31 live validation:

- `!research` now creates a fresh session when the goal changes instead of silently
  reusing the old active session
- `!next-paper` now completes cleanly through the deterministic router after the
  router timeout was raised to match source-fetch latency
- `!interpret` completes through the deterministic router, but it is materially
  slower than the other commands; the measured direct round-trip was about `67s`
- the `.44` helper now prints a waiting note for slow commands so the path feels
  less like a hang while interpretation is still running
- `!design` now completes cleanly through the deterministic router after the
  `latest` session-alias hardening in `workflow-api`
- `!preflight` is now also clean through the deterministic router and surfaces
  interpretation-aware warnings as intended

Operational note from the 2026-04-03 live validation:

- `!design` is now runner-first usable even without `!next-paper`
  because the backend can bootstrap an intake and interpretation directly from
  the current session goal
- `!run` now works for a technique-card-backed GPU design and submits a real
  Kubernetes Job through the approved workflow path
- `!launch-iteration` now works for the same DreamSim-style GPU path because the
  router/workflow path resolves to an allowed runner model template instead of
  trying to submit raw technique names as workflow models
- `!launch-batch` can now launch multiple bounded methodology variants in
  parallel through the same deterministic command seam
- `!decide-batch` can now record decisions for all ready completed iterations in
  one pass instead of requiring repeated `!decide-latest` calls
- `!decide-latest` now records a durable decision after the launched run
  completes and metrics are available

Current backend-owned one-shot transitions:

- `!start` -> `POST /research-sessions/start-literature-search`
- `!status` -> `GET /research-sessions/latest/context` plus
  `GET /research-sessions/latest/autoresearch-summary` when a campaign exists
- `!run` -> `POST /research-sessions/latest/transitions/run-happy-path`
- `!next` -> `POST /research-sessions/latest/transitions/advance-autoresearch`
- `!compare` -> `GET /research-sessions/latest/autoresearch-model-comparison`

Primary runner-first sequence:

```text
!start replicate DreamSim visual similarity metric with PyTorch and timm
!run
!next
!compare
```

Granular debug sequence remains available:

```text
!research replicate DreamSim visual similarity metric with PyTorch and timm
!design
!preflight
!run
!start-autoresearch
!draft-methodologies
!launch-batch
!decide-batch
!model-comparison
```
