# Glasslab Cluster Config

Glasslab is a runner-first ML research system built on a home Kubernetes lab.

The product is narrower than many of the older docs imply. The goal is not
general agent chat. The goal is:

- keep a bounded research session
- turn that session into a reviewable plan
- launch approved runs
- compare outcomes
- record a decision
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

The active product is `glasslab-v2`.

The canonical local command path is:

- `OpenCode`
- exo OpenAI-compatible serving
- repo-owned scripts
- `workflow-api`

The optional remote adapter path is:

- `whatsapp-gateway`
- `research-ingress`
- `research-command-router`
- `workflow-api`

The canonical control plane is:

- `workflow-api`

The canonical bounded inference lane is:

- exo OpenAI-compatible serving

There is no supported OpenClaw path in the current product.

## Primary Operator Loop

The intended primary loop is:

```text
!new <goal>
!add <source|note|dataset|baseline>
!plan
!check
!run
!compare
!decide <keep|discard|revise>
!next
```

Compatibility aliases may still exist:

- `!start`
- `!status`

But the docs should teach the newer session/plan-oriented loop.

## Start Here

If you want the current source of truth:

- [docs/glasslab-v2/current/README.md](docs/glasslab-v2/current/README.md)
- [docs/glasslab-v2/canonical-stack-2026-04.md](docs/glasslab-v2/canonical-stack-2026-04.md)
- [docs/glasslab-v2/system-map-2026-07.md](docs/glasslab-v2/system-map-2026-07.md)
- [docs/glasslab-v2/learning-task-flow.md](docs/glasslab-v2/learning-task-flow.md)
- [docs/glasslab-v2/local-model-command-surface.md](docs/glasslab-v2/local-model-command-surface.md)
- [docs/glasslab-v2/deprecated-api-surface-2026-07.md](docs/glasslab-v2/deprecated-api-surface-2026-07.md)
- [docs/glasslab-v2/ci-policy-2026-07.md](docs/glasslab-v2/ci-policy-2026-07.md)
- [docs/glasslab-v2/command-surface-spec.md](docs/glasslab-v2/command-surface-spec.md)
- [docs/glasslab-v2/router-and-backend-contract.md](docs/glasslab-v2/router-and-backend-contract.md)
- [docs/glasslab-v2/deprecation-map-2026-04.md](docs/glasslab-v2/deprecation-map-2026-04.md)

If you are operating the lab:

- `scripts/`
- `docs/glasslab-v2/runbooks/`
- `ansible/playbooks/`

If you need historical context:

- [docs/glasslab-v2/historical/README.md](docs/glasslab-v2/historical/README.md)
- [README-OLD.md](README-OLD.md)

## Canonical Environment

Important distinction:

- the canonical live environment is the provisioner at `192.168.1.44`
- this laptop checkout is a working client and Git copy
- ignored secrets, runtime bundles, imported images, and some operational truth
  still live only on `.44`

So:

- GitHub tells you committed repo state
- docs tell you the last documented live state
- only `.44` can confirm actual live state

## Current Design Rule

Glasslab does not need more competing paths.

It needs:

- one canonical command surface
- one canonical record store
- one canonical bounded experiment loop
- one honest statement about what literature support currently is
