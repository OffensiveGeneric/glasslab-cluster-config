# Intake Agent

`intake-agent` is a bounded stage-agent that normalizes raw intake requests before
later interpretation and design work.

Its job is narrow:

- accept one intake-create-style request
- return one bounded normalized intake draft
- preserve the explicit workflow candidate boundary

It does not:

- approve execution
- create runs
- interpret experimental claims
- mutate durable workflow state directly

The intended caller is `workflow-api`.

## Current Scope

Current implementation is a scaffold:

- `GET /healthz`
- `GET /approved-sources`
- `GET /paper-harvester/tracks`
- `GET /paper-harvester/papers`
- `POST /paper-harvester/plan`
- `POST /normalize-intake`
- deterministic normalization logic
- deterministic paper-harvester planning derived from the approved seed manifest
- response metadata describing the configured model backend and approved-source manifest

This is enough to make the service boundary real and testable before live model
integration is added.

## Seed Material

Tracked seed inputs for future literature or paper-harvesting work live under:

- `services/intake-agent/seeds/`

Current tracked seed manifest:

- `services/intake-agent/seeds/glasslab_paper_harvester_seed_manifest.yaml`

That manifest is the current approved-source and seed-paper list for the future
paper-puller / literature-harvester path. `intake-agent` now loads it at
runtime, exposes a normalized summary via `GET /approved-sources`, and surfaces
warning text when incoming `source_refs` point outside the currently approved
host list. It also exposes bounded harvester planning endpoints so a future
source-scout agent can ask for:

- approved track definitions and search queries
- filtered seed-paper lists
- a first bounded harvest plan by track/priority

It should be treated as tracked input data for bounded intake-side agent work,
not as a runtime secret.

## Intended Deployment Shape

- namespace: `glasslab-v2`
- deployment: `glasslab-intake-agent`
- service: `glasslab-intake-agent`
- service type: `ClusterIP`

## Environment

- `GLASSLAB_INTAKE_AGENT_PROVIDER_API`
- `GLASSLAB_INTAKE_AGENT_PROVIDER_BASE_URL`
- `GLASSLAB_INTAKE_AGENT_MODEL`
- `GLASSLAB_INTAKE_AGENT_TIMEOUT_SECONDS`
