# Glasslab Cluster Config

Glasslab is a runner-first ML research system built on a home Kubernetes lab.

The run fabric is deliberately narrow, but the product-level object is now an
investigation. The goal is not general agent chat. The goal is:

- keep a bounded investigation with explicit hypotheses
- turn it into a reviewable plan
- freeze an approved plan before execution
- launch approved runs
- compare outcomes
- record a decision
- link claims to exact run artifacts
- propose the next bounded mutation

## Repo Layout

- `ansible/`
  - host bootstrap, maintenance, GPU prep
- `kubeadm/`
  - cluster manifests, especially `glasslab-v2`
- `services/`
  - backend services and bounded operators
- `scripts/`
  - deploy, export, sync, smoke-test helpers
- `docs/`
  - architecture notes, runbooks, current-state docs, and historical notes

Useful service buckets:

- control plane:
  - `services/workflow-api`
  - `services/workflow-registry`
  - `services/evaluator`
  - `services/reporter`
- command surface:
  - `services/whatsapp-gateway`
  - `services/research-ingress`
  - `services/research-command-router`
- bounded stage agents:
  - `services/intake-agent`
  - `services/interpretation-agent`
  - `services/assessment-agent`
  - `services/design-agent`

## Canonical Product Direction

The first bounded Honeydew/Beaker research workflow is documented in
[`docs/research-orchestrator.md`](docs/research-orchestrator.md). It adds a
durable outer research state machine around isolated OpenCode runtimes and the
existing bounded cluster-execution service. The Titanic stack remains legacy
v1 reference material.

The current Discord and operator commands, arbitrary-task intake limits, and
live progress are summarized in
[`docs/research-orchestrator-command-surface.md`](docs/research-orchestrator-command-surface.md).

The active product is the `glasslab-v2` research orchestrator.

The canonical human research path is:

- Discord
- `research-orchestrator`
- isolated Honeydew and Beaker OpenCode runtimes
- exo OpenAI-compatible model serving
- `workflow-api`
- bounded Kubernetes Jobs

OpenCode is the agents' inner tool-use runtime, not the durable workflow or
human approval surface. `workflow-api` remains the canonical cluster execution
control plane. WhatsApp, OpenClaw, and the older command-router path are
compatibility or historical material rather than the current research front
door.

## Primary Operator Loop

The intended primary loop is:

```text
question
  -> hypotheses
  -> immutable execution-graph plan
  -> explicit approval
  -> dependency-checked bounded runs
  -> verified evidence bundles
  -> claim and next experiment
```

Discord is the primary human surface. The research orchestrator's database and
append-only event log are authoritative; Discord is their operator-facing
projection. OpenCode remains internal to Honeydew and Beaker.

## Start Here

If you want the current source of truth:

- [HARDWARE-INVENTORY.md](HARDWARE-INVENTORY.md) for the live LAN hardware,
  storage, GPU, and managed-access inventory
- [AGENTS.md](AGENTS.md) for the concise coding-agent and contributor handoff
- [HANDOFF.md](HANDOFF.md) for the summarized current implementation checkpoint
- [TODO.md](TODO.md) for the prioritized index into the GitHub Issues work queue
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/glasslab-v2/current/README.md](docs/glasslab-v2/current/README.md)
- [docs/glasslab-v2/canonical-stack-2026-04.md](docs/glasslab-v2/canonical-stack-2026-04.md)
- [docs/glasslab-v2/system-map-2026-07.md](docs/glasslab-v2/system-map-2026-07.md)
- [docs/glasslab-v2/learning-task-flow.md](docs/glasslab-v2/learning-task-flow.md)
- [docs/glasslab-v2/investigation-api-v1.md](docs/glasslab-v2/investigation-api-v1.md)
- [docs/glasslab-v2/local-model-command-surface.md](docs/glasslab-v2/local-model-command-surface.md)
- [docs/glasslab-v2/deprecated-api-surface-2026-07.md](docs/glasslab-v2/deprecated-api-surface-2026-07.md)
- [docs/glasslab-v2/ci-policy-2026-07.md](docs/glasslab-v2/ci-policy-2026-07.md)
- [docs/glasslab-v2/command-surface-spec.md](docs/glasslab-v2/command-surface-spec.md)
- [docs/research-orchestrator-command-surface.md](docs/research-orchestrator-command-surface.md)
- [docs/glasslab-v2/router-and-backend-contract.md](docs/glasslab-v2/router-and-backend-contract.md)
- [docs/glasslab-v2/deprecation-map-2026-04.md](docs/glasslab-v2/deprecation-map-2026-04.md)

If you are operating the lab:

- `scripts/`
- `docs/glasslab-v2/runbooks/`
- `ansible/playbooks/`

## Canonical Environment

Important distinction:

- `glasslab.org` is the public SSH gateway
- the canonical live environment is the provisioner at `192.168.1.44`
- the gateway and provisioner are separate machines
- this laptop checkout is a working client and Git copy
- ignored secrets, runtime bundles, imported images, and some operational truth
  still live only on `.44`

See [docs/access-topology.md](docs/access-topology.md) for canonical host and
SSH names.

So:

- GitHub tells you committed repo state
- docs tell you the last documented live state
- only `.44` can confirm actual live state

## Current Design Rule

Glasslab does not need more competing paths.

It needs:

- one canonical command surface
- one canonical investigation record
- one canonical record store
- one canonical bounded experiment loop
- one honest statement about what literature support currently is
