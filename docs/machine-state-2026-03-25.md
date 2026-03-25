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
  - `/tmp` briefly filled with stale image tarballs during the live rollout and had to be cleaned before OpenClaw could be re-exported

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
- current note:
  - legacy in-cluster `vllm` was retired during this session
  - `kubectl describe node node02` now shows `nvidia.com/gpu     0         0` under allocated resources
  - this GPU lane is now free for future bounded backend work, including a later GPU-capable neural-net workflow

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
  - heavier external inference host
  - larger-model backend candidate for bounded research stages
- validated state:
  - `qwen3:30b` installed
  - native tool support available
  - no longer the active interactive OpenClaw chat backend

### `192.168.1.12`

- role:
  - primary interactive OpenClaw chat backend
  - bounded ranker host
- validated state:
  - native Ollama serving `qwen3:14b`
  - ranker service healthy on `:8181`
  - current `workflow-api` ranker target
  - current OpenClaw provider target

## Current Practical Role Split

As of the 2026-03-25 remote session:

- `.44`: canonical admin, deploy, image-build, and image-import host
- `.23`: heavier inference host for later bounded research stages
- `.12`: OpenClaw chat backend and bounded ranker backend
- `node04`: live `workflow-api` and interpretation-agent host
- `node05`: live intake-agent and schedule-worker host
- `node01`: live OpenClaw host
- `node02`: reclaimed GPU worker; no longer occupied by legacy `vllm`
