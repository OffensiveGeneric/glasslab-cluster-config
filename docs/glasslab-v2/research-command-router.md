# Research Command Router

`research-command-router` is the explicit answer to the command-routing failures we
saw with OpenClaw. It is a narrow HTTP service that accepts a user message,
matches a small set of deterministic research commands, and calls `workflow-api`
directly.

Current commands:

- `!research <topic>`
- `!more-papers`
- `!next-paper`
- `!add-paper <url|title>`
- `!session`
- `!note <text>`
- `!op`
- `!help`

Current contract:

- `POST /dispatch`
- request: `{ "message": "...", "submitted_by": "optional" }`
- response:
  - `matched`
  - `forward_to_openclaw`
  - `command`
  - `response_text`
  - `workflow_api_endpoint`
  - `payload`

This service is intentionally useful even before it is fully wired into the
WhatsApp ingress path. It gives Glasslab a real deterministic front-door
contract instead of relying on the operator model to notice and honor commands.

Important boundary:

- today, the WhatsApp/OpenClaw path still does **not** invoke this service first
- that means command handling in chat is still partially model-dependent
- the next integration step is to place this service in front of OpenClaw for
  explicit `!` commands and only forward non-command turns to the operator shell
