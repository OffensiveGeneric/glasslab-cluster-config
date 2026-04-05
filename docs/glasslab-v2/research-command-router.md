# Research Command Router

`research-command-router` is the explicit answer to the command-routing failures we
saw with OpenClaw. It is a narrow HTTP service that accepts a user message,
matches a small set of deterministic research commands, and calls `workflow-api`
directly.

Current commands:

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
- `!note <text>`
- `!op`
- `!help`

Recommended primary runner flow:

- `!start <topic>`
- `!run`
- `!next`
- `!compare`

The older granular commands remain available for debugging and operator control.

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

Validated blocker from `.44` on 2026-03-29:

- the existing OpenClaw CLI does **not** support deterministic WhatsApp polling
  through `openclaw message read`
- probe result:
  - `openclaw message read --channel whatsapp ...`
  - returns `Error: Message action read not supported for channel whatsapp.`
- so the practical integration options are narrower than they first looked:
  - patch OpenClaw itself to intercept `!` commands before agent execution, or
  - replace the WhatsApp front door with a repo-owned ingress that handles
    commands directly and only forwards non-command traffic to OpenClaw

This means the new router service is the correct deterministic contract, but the
remaining work is now explicitly an ingress-ownership decision rather than a
small prompt/config tweak.
