# Tool Choice Exposure Options

This note exists to narrow issue `#11`.

The question is not whether `tool_choice` would be useful.

It would.

The question is which path is realistic for Glasslab.

## Current validated boundary

The current reachable OpenClaw operator path does not expose `tool_choice`.

Validated in `docs/glasslab-v2/tool-calling-reliability.md`:

- `openclaw gateway call agent --params ...` rejects `tool_choice`
- `openclaw gateway call chat.send --params ...` also rejects `tool_choice`
- bundled OpenClaw code still contains internal `tool_choice` handling

So the blocker is not just the higher-level CLI wrapper.

The blocker is the reachable gateway request schema.

## Realistic options

### 1. Patch the reachable gateway schema

This is the cleanest answer if Glasslab wants true pinned-tool experiments.

Desired outcome:

- the reachable `agent` or `chat.send` path accepts `tool_choice`
- Glasslab can force:
  - `required`
  - or a specific function name

Pros:

- directly answers the current experiment question
- separates tool-selection ambiguity from argument-generation quality
- keeps the experimental path honest

Cons:

- likely requires carrying an OpenClaw patch or custom build
- creates version-drift and maintenance cost

## 2. Find a supported lower-level API

This is only viable if a documented request path already exists but was not the one used during the live audit.

Current status:

- no validated lower-level path has been found yet
- runtime YAML and prompt/config changes do not appear sufficient

Pros:

- avoids a custom build if it exists

Cons:

- still hypothetical until proven

## 3. Keep production on no-arg wrappers

This is the safest near-term operating policy even if option 1 is pursued experimentally.

Use:

- repo-managed no-arg wrappers for state-changing actions
- tiny read-only argumented tools only as experiments

Pros:

- already matches the measured reliable path
- avoids widening the production control surface

Cons:

- does not answer the pinned-tool experiment question by itself

## Recommended split

Use two tracks instead of forcing one answer:

1. production operator path:

- keep the current narrow no-arg default

2. experimental tool-choice path:

- only pursue if Glasslab is willing to carry either:
  - a custom OpenClaw patch
  - or a newly validated lower-level API

This keeps the production gateway conservative while still allowing a clean experiment later.

## Practical next step

The next bounded task for this issue should be:

- inspect the current OpenClaw version/build path and decide whether Glasslab is willing to carry a tiny schema-exposure patch for experimental use

If the answer is no, the issue should remain explicitly deferred and Glasslab should continue using repo-managed no-arg wrappers instead of treating `tool_choice` as imminently available.
