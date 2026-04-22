# Research Command Router

This service is the deterministic front door for the supported Glasslab command
surface.

It owns explicit command traffic such as:

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

The current contract is:

- `POST /dispatch` with the inbound user message
- command router matches a supported explicit command
- router calls `workflow-api` directly
- router returns `response_text` suitable for chat plus the structured backend payload
- unsupported or non-command text returns a deterministic rejection that points
  the user back to `!help`

This service intentionally does not provide free-form chat fallback.
