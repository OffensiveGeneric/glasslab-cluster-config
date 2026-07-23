# Command Surface Spec

This document defines the operator-facing command structure for Glasslab.

The command surface should reflect the actual research loop, not historical implementation details.

The command vocabulary is backend-owned. It can be invoked from OpenCode,
scripts, or a remote adapter such as WhatsApp.

The primary local operator surface is now OpenCode talking to the lab
exo/OpenAI-compatible model endpoint and using repo-owned scripts to call
`workflow-api`.

WhatsApp is a secondary remote adapter, not the required surface for job
control.

## Design principle

Commands should represent:

* operator intentions
* stable backend transitions
* durable session actions

Commands should not expose:

* internal pipeline staging details
* implementation-era debugging assumptions
* literature-first product framing

## Primary command set

### `!new <goal>`

Create a fresh research session and pin it to the sender.

Examples:

* `!new replicate DreamSim on a bounded art similarity dataset`
* `!new compare two bounded artist-similarity baselines`

Expected behavior:

* create session
* persist goal statement
* pin session to sender
* return session summary and suggested next step

Compatibility alias:

* `!start`

### `!state`

Return the current session state in operator language.

Expected output includes:

* session goal
* sources count
* current plan status
* run readiness
* latest run summary
* next suggested action

Compatibility alias:

* `!status`

### `!add <thing>`

Generic intake command for sources, notes, datasets, and baselines.

Examples:

* `!add https://arxiv.org/abs/2410.07095`
* `!add https://example.org/paper.pdf`
* `!add dataset: s3://datasets/paintings/v1`
* `!add note: keep timm backbones only`
* `!add baseline: DreamSim`

Expected behavior:

* infer intake type
* persist source or note
* attach to pinned session
* return what was recorded and whether it changes plan readiness

### `!plan`

Create or refresh the current bounded design draft from session state.

Expected behavior:

* use current session goal and added inputs
* materialize one current design
* report workflow family, objective, candidate models, and missing inputs

### `!check`

Run preflight on the current design without launching a run.

Expected behavior:

* report `ready_for_run` or explicit blockers
* keep output short and actionable

### `!run`

Launch the current approved design.

Expected behavior:

* prepare design if needed
* validate readiness
* create run
* submit run
* return run id and workflow family

### `!compare`

Compare the current relevant runs in the pinned session.

Optional explicit form:

* `!compare run-123 run-124`

Expected behavior:

* return best metric summary
* return strongest baseline summary
* suggest next decision

### `!decide <keep|discard|revise>`

Record an explicit human decision for the current run or comparison state.

Examples:

* `!decide keep`
* `!decide discard`
* `!decide revise`

Future explicit form may allow:

* `!decide keep run-124`
* `!decide revise use a smaller head`

### `!next`

Advance the current bounded campaign by proposing and optionally launching the next mutation.

Expected behavior:

* use session and decision state
* draft bounded variants if needed
* launch next approved variants if eligible
* summarize what changed

### `!note <text>`

Persist a durable session note.

Example:

* `!note prioritize style drift robustness over nearest-neighbor accuracy`

## Supporting commands

These are allowed but secondary.

### `!find <query>`

Optional discovery helper.

This is not the product center.

### `!sources`

List current source records attached to the session.

### `!runs`

List current runs for the pinned session.

### `!artifacts`

List artifacts for the latest or selected run.

### `!resume [session-id]`

Resume an explicit session or re-pin the latest sender-owned session.

## Removed command surface

The following older command families are not supported going forward:

* literature/debug commands such as `!research`, `!more-papers`, `!next-paper`
* staging/debug commands such as `!interpret`, `!design`, `!preflight`
* batch/autoresearch control commands such as `!start-autoresearch`, `!launch-batch`, `!decide-batch`
* raw/operator debug commands such as `!op`, `!health`, `!raw`

## Session rule

Once a sender has a pinned session:

* all primary commands operate on that pinned session by default
* `latest` may remain as an internal compatibility alias
* `latest` should not be the main product story

## Default teaching sequence

The command surface should teach this loop:

1. `!new <goal>`
2. `!add <one or two useful things>`
3. `!plan`
4. `!check`
5. `!run`
6. `!compare`
7. `!decide keep|discard|revise`
8. `!next`
