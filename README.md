# Glasslab Cluster Config

Glasslab is a runner-first ML research system built on a home Kubernetes lab.

The current goal is not “general AI research chat.” It is narrower:

- take a concrete problem statement
- turn it into a bounded execution contract
- launch approved experiment variants
- compare them
- keep iterating while we are away

## What This Repo Contains

- `ansible/`: host bootstrap, maintenance, GPU prep
- `kubeadm/`: cluster manifests, especially `glasslab-v2`
- `services/`: backend services, runner code, OpenClaw runtime config
- `scripts/`: deploy, export, sync, smoke-test helpers
- `docs/`: architecture notes, runbooks, live-state notes

## Current Product Direction

The active product is `glasslab-v2`, centered on:

- `workflow-api`: session state, interpretation, design, run creation, autoresearch
- `workflow-registry`: approved workflow templates
- `runner`: bounded execution on the cluster
- `research-command-router` and `research-ingress`: deterministic command seam
- `whatsapp-gateway`: repo-owned chat/control shell for deterministic command turns

OpenClaw is no longer treated as core to the critical experiment-runner path.
It may remain useful later as an optional conversational surface, but the
near-term product direction is to keep command/control deterministic and
backend-owned.

The main loop we are building is:

1. start from a problem statement or manually added source
2. derive bounded `TechniqueKnowledge` and `MethodSpec`
3. launch approved run variants
4. compare results
5. propose and launch the next bounded mutations

## Current Focus

The current focus is the experiment-runner side:

- technique cards imported from curated methodology knowledge
- bounded interpretation output
- GPU-ready design/run handoff
- parallel autoresearch batches
- deterministic comparison and follow-on mutation proposals

The literature side exists, but it is secondary for now. Manual source addition is acceptable if it gets us to better runs faster.

## Primary Operator Flow

The happy-path command surface is now intentionally small:

```text
!start <topic>
!run
!next
!compare
!status
```

The older granular commands still exist for debugging, but they are no longer the primary UX.

## Canonical Environment

Important distinction:

- the canonical live environment is the provisioner at `192.168.1.44`
- this laptop checkout is a working client and Git copy
- ignored secrets, runtime bundles, imported images, and some operational truth still live only on `.44`

So:

- GitHub tells you committed repo state
- docs tell you the last documented live state
- only `.44` can confirm actual live state

## Where To Start

If you want the current architecture and direction:

- [docs/glasslab-v2/README.md](docs/glasslab-v2/README.md)
- [docs/glasslab-v2/overview.md](docs/glasslab-v2/overview.md)
- [docs/glasslab-v2/bounded-experiment-runner-priority.md](docs/glasslab-v2/bounded-experiment-runner-priority.md)
- [docs/glasslab-v2/runner-first-technique-knowledge-plan.md](docs/glasslab-v2/runner-first-technique-knowledge-plan.md)
- [docs/glasslab-v2/technique-catalog.md](docs/glasslab-v2/technique-catalog.md)
- [docs/glasslab-v2/openclaw-deprecation-and-custom-whatsapp-plan.md](docs/glasslab-v2/openclaw-deprecation-and-custom-whatsapp-plan.md)
- [docs/glasslab-v2/custom-chat-shell-plan.md](docs/glasslab-v2/custom-chat-shell-plan.md)
- [docs/glasslab-v2/live-state-2026-04-03.md](docs/glasslab-v2/live-state-2026-04-03.md)

If you want the concrete first target problem:

- [docs/glasslab-v2/artist-similarity-v1.md](docs/glasslab-v2/artist-similarity-v1.md)
- [docs/glasslab-v2/examples/artist-similarity-technique-cards.json](docs/glasslab-v2/examples/artist-similarity-technique-cards.json)

If you are operating the lab:

- `scripts/`
- `docs/glasslab-v2/runbooks/`
- `ansible/playbooks/`

## Legacy Material

The previous longer root README is preserved at [README-OLD.md](README-OLD.md).
