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

Current deterministic happy-path ownership:

- `whatsapp-gateway` owns sender/session transcript handling
- `research-ingress` owns inbound routing
- `research-command-router` owns command matching and dispatch
- `workflow-api` owns the backend transitions for the primary five commands

For `!start`, `!status`, `!run`, `!next`, and `!compare`, the command turn does
not depend on OpenClaw.

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

- deterministic `!` commands now belong on the repo-owned ingress path
- only non-command turns should fall through to OpenClaw
- do not widen the router into a general agent/tool surface; keep command turns
  narrow and backend-owned

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
