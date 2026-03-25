# Machine State: 2026-03-25

This note records the machine-level state observed during the 2026-03-25 remote session.

It is meant to complement `live-state-2026-03-25.md` by keeping the current machine roles in one place.

## Provisioner

### `192.168.1.44` `glasslab-PXE-01`

- role:
  - PXE / provisioner host
  - bastion
  - canonical repo checkout
  - `kubectl` admin workstation
- validated state:
  - reachable through the `glasslab.org -> .44` path
  - Docker build path works
  - node image import wrappers are usable from this host

## Kubernetes Nodes

Validated from `.44`:

### `192.168.1.48` `node01`

- role:
  - Kubernetes worker
  - image-import target for local Glasslab images

### `192.168.1.11` `node02`

- role:
  - Kubernetes worker
  - active NVIDIA GPU host
  - legacy in-cluster `vllm` host
- current note:
  - still not reclaimed for bounded-agent work

### `192.168.1.50` `node03`

- role:
  - Kubernetes worker
  - image-import target for local Glasslab images

### `192.168.1.51` `node04`

- role:
  - Kubernetes worker
  - active NVIDIA GPU host
- currently hosting:
  - `glasslab-workflow-api`
  - `glasslab-interpretation-agent`

### `192.168.1.47` `node05`

- role:
  - Kubernetes worker
  - current unattended-backend landing area in practice
- currently hosting:
  - `glasslab-nats`
  - `glasslab-intake-agent`
  - `glasslab-schedule-worker`

## Mac Service Hosts

These hosts are not Kubernetes workers.

### `192.168.1.23`

- role:
  - primary external inference host
  - current native-Ollama OpenClaw backend
- validated state:
  - `qwen3:30b` installed
  - native tool support available to OpenClaw on this path

### `192.168.1.12`

- role:
  - secondary model host
  - bounded ranker host
- validated state:
  - ranker service healthy on `:8181`
  - current `workflow-api` ranker target

## Current Practical Role Split

As of the 2026-03-25 remote session:

- `.44`: canonical admin, deploy, image-build, and image-import host
- `.23`: main OpenClaw inference backend
- `.12`: bounded ranker backend
- `node04`: live `workflow-api` and interpretation-agent host
- `node05`: live intake-agent and schedule-worker host
- `node02`: still occupied by legacy `vllm`
