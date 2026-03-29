# Research Command Router

This service is the deterministic front door for the narrow research-loop commands
that were too flaky when routed through OpenClaw's model/tool-selection path.

It is intended to sit in front of OpenClaw for explicit command traffic such as:

- `!research <topic>`
- `!more-papers`
- `!next-paper`
- `!add-paper <url|title>`
- `!session`
- `!note <text>`
- `!op`
- `!help`

The current contract is:

- `POST /dispatch` with the inbound user message
- command router matches a supported explicit command
- router calls `workflow-api` directly
- router returns `response_text` suitable for chat plus the structured backend payload
- non-command text returns `forward_to_openclaw=true`

This is deliberately more limited than OpenClaw chat. It exists to make the
critical research-session path deterministic.
