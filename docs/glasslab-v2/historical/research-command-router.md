# Research Command Router

`research-command-router` is the deterministic command matcher for the primary
Glasslab operator loop.

It accepts one inbound message, matches the supported command surface, and
dispatches exactly one backend-owned action in `workflow-api`.

## Supported commands

- `!new <goal>`
- `!state`
- `!add <thing>`
- `!plan`
- `!check`
- `!run`
- `!compare`
- `!decide <keep|discard|revise>`
- `!next`
- `!help`

Compatibility aliases:

- `!start -> !new`
- `!status -> !state`

Unsupported and non-command turns are rejected deterministically with a compact
`Use !help` response.

## Contract

- `POST /dispatch`
- request:
  - `message`
  - `submitted_by`
  - optional `session_id`
- response:
  - `matched`
  - `command`
  - `response_text`
  - `workflow_api_endpoint`
  - `payload`

## Boundary

The router is not a workflow engine and it is not a chat backend.

It should:

- recognize the supported command surface
- preserve sender-pinned session behavior by honoring `session_id` when present
- dispatch one backend-owned action
- return compact operator text

It should not:

- orchestrate multi-step fallback flows
- expose debug commands as supported surface area
- invent conversational fallback behavior
