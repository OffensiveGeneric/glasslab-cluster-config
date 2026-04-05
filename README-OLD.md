# Glasslab Cluster Config

This repo is the committed control plane for the Glasslab lab.

The important distinction:

- the canonical live environment is the provisioner at `192.168.1.44`
- this repo is the committed description of that environment
- some operational truth still exists only on `.44`, including ignored secrets, exported runtime bundles, imported images, and any unpushed changes

If you are trying to remember what this system is, start here:

- `docs/operator-orientation.md`
- `docs/glasslab-system-spec-for-research.md`

## The Short Version

Glasslab currently contains two related stacks:

- `v1`: a legacy/reference Titanic experiment stack using a FastAPI agent API, vLLM, a fixed runner, and Kubernetes Jobs
- `v2`: a cleaner workflow platform built around `workflow-api`, a Git-backed workflow registry, deterministic evaluator/reporter services, OpenClaw as the operator gateway, persistent core service state, shared NFS-backed datasets/artifacts, and a live no-arg intake -> design -> run operator path

The repo is large because it includes both platform infrastructure and application-layer workflow services.

## How To Read The Repo

- `ansible/`
  Host bootstrap, SSH hardening, GPU enablement, and maintenance.
- `docs/`
  Human-readable architecture, runbooks, validation notes, and current assumptions.
- `kubeadm/`
  Cluster manifests for shared components, the v1 agent stack, and `glasslab-v2`.
- `live-config/`
  Tracked snapshots of provisioner-side config such as PXE and autoinstall state.
- `scripts/`
  Operational wrappers for deploy, smoke-test, export, sync, and validation flows.
- `services/`
  Actual backend services, runner code, shared schemas, and OpenClaw runtime config.

## Current Working Mental Model

Think about the system in four layers:

1. Infrastructure
   PXE, autoinstall, Ansible, Kubernetes, GPU enablement.
2. Execution
   Jobs, runner images, vLLM, storage paths, artifact locations.
3. Backend logic
   `workflow-api`, workflow registry, evaluator, reporter.
4. Operator gateway
   OpenClaw config, prompts, bindings, and chat-channel entrypoints.

If you want the deeper explanation, read:

- `docs/operator-orientation.md`
- `docs/glasslab-v2/overview.md`
- `docs/glasslab-v2/cluster-primitives-gap-audit.md`
- `docs/live-state-2026-03-23.md`
- `docs/glasslab-v2/network-storage-integration.md`
- `docs/glasslab-v2/intake-design-run-implementation-plan.md`

## Current Machines

- `192.168.1.44` (`glasslab-PXE-01`): provisioner, bastion, Ansible control host, kubectl admin workstation
- `192.168.1.49` (`cp01`): Kubernetes control plane
- `192.168.1.48` (`node01`): Kubernetes worker and active NVIDIA GPU worker
- `192.168.1.11` (`node02`): Kubernetes worker and active NVIDIA GPU worker
- `192.168.1.50` (`node03`): Kubernetes worker
- `192.168.1.51` (`node04`): Kubernetes worker and active NVIDIA GPU worker
- `192.168.1.47` (`node05`): Kubernetes worker and CPU-only in practice because its visible NVIDIA card would require the legacy 470 driver path

## Current Repo-Documented State

This is not a substitute for checking `.44`.

- the cluster is a single-control-plane Kubernetes lab using Calico
- `node01`, `node02`, and `node04` are documented as active NVIDIA workers
- `glasslab-agents` contains the older Titanic stack, which should now be treated as legacy/reference scaffolding rather than the main platform direction
- `glasslab-v2` contains the newer workflow platform direction
- the current live-state report from `.44` is in `docs/live-state-2026-03-23.md`
- OpenClaw is live in the cluster as an internal operator gateway, even though the committed Deployment manifest still keeps `replicas: 0` as the safe default posture
- WhatsApp is active in the live OpenClaw path
- shared NFS-backed datasets and artifacts are now available in `glasslab-v2`, with a tracked 5Ti reservation split across datasets and artifacts
- Postgres, MinIO, OpenClaw state, and NATS now persist across pod replacement instead of depending on `emptyDir`
- `workflow-api` now pulls from private GHCR instead of depending on `node03`-local image import
- the first no-arg OpenClaw path now covers intake, design draft creation, accepted run creation, and follow-up status/artifact/log inspection

## Best Entry Points

If you are resuming work:

1. `docs/operator-orientation.md`
2. `docs/glasslab-v2/README.md`
3. `docs/live-state-2026-03-23.md`
4. `docs/titanic-agent-stack.md`
5. `docs/gpu-workers.md`

If you are operating the lab from `.44`:

1. `scripts/`
2. `docs/glasslab-v2/runbooks/`
3. `ansible/playbooks/`
