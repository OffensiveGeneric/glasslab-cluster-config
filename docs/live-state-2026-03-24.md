# Live State Report: 2026-03-24

This note records what was validated from `.44` during the 2026-03-24 lab session.

It should be treated as a newer documented live-state checkpoint than `live-state-2026-03-23.md`.

## Core Cluster

Validated from `.44`:

- `cp01` is `Ready`
- `node01` is `Ready`
- `node02` is `Ready`
- `node03` is `Ready`
- `node04` is `Ready`
- `node05` is `Ready`

The live cluster is still on:

- Kubernetes `v1.35.2`

## GPU Allocatable Snapshot

Validated allocatable GPU state:

- `node01`: `nvidia.com/gpu=1`
- `node02`: `nvidia.com/gpu=1`
- `node04`: `nvidia.com/gpu=1`

Nodes without allocatable GPU at check time:

- `cp01`
- `node03`
- `node05`

## Glasslab v2

Validated from `.44`:

- `glasslab-postgres` is `Running` on `node01`
- `glasslab-minio` is `Running` on `node01`
- `glasslab-nats` is `Running` on `node05`
- `glasslab-workflow-api` is `Running` on `node01`

Observed service posture:

- all current `glasslab-v2` Services remain `ClusterIP`
- `glasslab-openclaw` Service still exists
- `glasslab-openclaw` is now back at `1` replica after the Mac-backed inference cutover

## OpenClaw

Validated from `.44`:

- the live Deployment points at the pinned OpenClaw image digest
- OpenClaw has been reconfigured to use the Mac-backed inference endpoint on `192.168.1.23`
- the live Deployment is currently scaled up and healthy
- the first Mac cutover used Ollama's OpenAI-compatible `/v1` endpoint
- direct chat against that endpoint works
- the current OpenClaw tool-calling harness does not work on that path
- the observed failure is:
  - `400 registry.ollama.ai/library/deepseek-r1:32b does not support tools`

That means the live `.23` cutover currently improves plain inference, but it is not yet a drop-in replacement for the earlier tool-calling path.

## Model Serving

Validated from `.44`:

- the in-cluster `vllm` pod is still `Running`
- the live pod is `vllm-6b78cbb67f-dcx2p`
- it is scheduled on `node02`

That means the older in-cluster model-serving path still exists even though the active OpenClaw path has been moved to the external Mac-backed endpoint.

## Workflow Jobs

Observed in `glasslab-v2`:

- completed `generic-tabular-benchmark` Jobs are present
- completed `literature-to-experiment` Jobs are present

This is consistent with the backend-owned execution path continuing to submit real Kubernetes Jobs.

## Mac Studio Sidecar Capacity

Observed directly on the lab network during the same session:

- `192.168.1.23` is a `Mac Studio` with `Apple M4 Max` and `64 GB` memory
- that host is running Ollama and is now the primary external inference host with `deepseek-r1:32b`
- a second model pull for `qwen3:30b` has been started there as the next native-Ollama tool candidate
- `192.168.1.12` is a second `Mac Studio` with `Apple M4 Max` and `48 GB` memory
- that host is running Ollama with `qwen3:14b`
- that host is also serving a bounded ranker endpoint on `:8181`
- `.12` `qwen3:14b` was also validated to return native Ollama `tool_calls` on `/api/chat`

These hosts are not Kubernetes workers.

Treat them as separate service hosts unless a later design decision changes that.

## Provisioner Repo Reality

Validated from `.44`:

- the canonical provisioner checkout at `/home/glasslab/cluster-config` is currently behind `origin/main`
- the provisioner worktree also has local modifications

This matters operationally because:

- GitHub is not the only truth
- `.44` also contains unpushed and in-progress state
- any deploy or validation claim should be grounded in the provisioner checkout first
