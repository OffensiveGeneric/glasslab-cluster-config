# Machine State: 2026-03-24

This note records the machine-level state observed during the 2026-03-24 lab session.

It is meant to complement `live-state-2026-03-24.md` by keeping the host inventory and current machine roles in one place.

## Provisioner

### `192.168.1.44` `glasslab-PXE-01`

- role:
  - PXE / provisioner host
  - bastion
  - canonical repo checkout
  - `kubectl` admin workstation
- validated state:
  - host reachable
  - canonical repo path still `/home/glasslab/cluster-config`
  - cluster reachable from this host

## Kubernetes Nodes

Validated from `.44`:

### `192.168.1.49` `cp01`

- role:
  - Kubernetes control plane
- state:
  - `Ready`
  - Kubernetes `v1.35.2`

### `192.168.1.48` `node01`

- role:
  - Kubernetes worker
  - current v2 stateful-service host in practice
- state:
  - `Ready`
  - currently hosting:
    - `glasslab-postgres`
    - `glasslab-minio`
    - `glasslab-openclaw`
    - `glasslab-workflow-api`

### `192.168.1.11` `node02`

- role:
  - Kubernetes worker
  - active NVIDIA GPU host
  - current legacy in-cluster vLLM host
- state:
  - `Ready`
  - allocatable:
    - `cpu: 8`
    - `memory: ~64 GiB`
    - `nvidia.com/gpu: 1`
  - currently hosting:
    - `glasslab-agents/vllm`
  - current operational note:
    - OpenClaw no longer depends on this node for its active inference path
    - but the old `vllm` pod is still running here and still reserves the GPU

### `192.168.1.50` `node03`

- role:
  - Kubernetes worker
- state:
  - `Ready`
  - no special live role observed during this check

### `192.168.1.51` `node04`

- role:
  - Kubernetes worker
  - active NVIDIA GPU host
- state:
  - `Ready`

### `192.168.1.47` `node05`

- role:
  - Kubernetes worker
  - current v2 batch-job / NATS host in practice
- state:
  - `Ready`
  - currently hosting:
    - `glasslab-nats`
    - completed benchmark and literature Jobs

## Mac Service Hosts

These hosts are not Kubernetes workers.

### `192.168.1.23` `CS60140N7311`

- hardware:
  - `Mac Studio`
  - `Apple M4 Max`
  - `64 GB` memory
- role:
  - primary external inference host
- Ollama state:
  - `deepseek-r1:32b` installed
  - direct chat works
  - native tool calling does not work for `deepseek-r1:32b`
  - observed native error:
    - `registry.ollama.ai/library/deepseek-r1:32b does not support tools`
- current follow-up:
  - `qwen3:30b` pull is in progress
  - a `launchd` watchdog is installed to restart the pull if it stalls
  - observed pull state during this check:
    - about `159 MB / 18 GB`
    - `~19G` total `.ollama` size on disk

### 2026-03-25 Remote Update

- host is reachable again through the `glasslab.org -> .44 -> .23` path
- `qwen3:30b` is still not installed yet
- a direct `ollama pull qwen3:30b` was revalidated as healthy at about `10-12 MB/s`
- the previous `launchd` watchdog was misleading because it repeatedly reported restart activity without providing a stable operator-facing status signal
- a simpler persistent pull loop is now running instead:
  - script path: `/tmp/qwen3-30b-pull-loop.sh`
  - process shape: `/bin/zsh /tmp/qwen3-30b-pull-loop.sh`
  - log path: `/tmp/qwen3-30b-pull-loop.log`
- observed live pull state during the 2026-03-25 remote check:
  - about `534 MB / 18 GB`
  - about `3%`
  - estimated remaining time in Ollama output: about `25 minutes`

### `192.168.1.12` `CS60123N7311`

- hardware:
  - `Mac Studio`
  - `Apple M4 Max`
  - `48 GB` memory
- role:
  - secondary inference host
  - live ranker host
  - first proven native-Ollama tool candidate
- Ollama state:
  - `qwen3:14b` installed
  - `/v1/models` returns `qwen3:14b`
  - native `/api/chat` tool probing returned structured `tool_calls`
- additional live service:
  - bounded ranker on `http://192.168.1.12:8181`
  - `GET /healthz` returns `{"status":"ok"}`

## Current Practical Role Split

As of the end of the 2026-03-24 session:

- `.44`: canonical admin / deploy / bastion host
- `node01`: current v2 service host
- `node02`: still occupied by legacy in-cluster `vllm`
- `node05`: NATS and completed workload landing area
- `.23`: stronger external chat inference host
- `.12`: ranker host and first proven native-Ollama tool-capable Mac

## Most Important Operational Caveat

The live system currently has two different inference realities:

- active OpenClaw chat inference is on `.23`
- the old in-cluster `vllm` path still exists on `node02`

So "Mac cutover complete" is true for chat inference, but not yet true for full tool-path replacement or GPU-node reclamation.
