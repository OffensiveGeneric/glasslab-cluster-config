# Mac Service Host Boundary

This note narrows issue `#32`.

The practical question is not whether the Macs are useful.

They are.

The real question is how to use them without creating a second infrastructure project.

## Current decision

Use the Macs as separate service hosts.

Do not treat them as kubeadm workers in the current phase.

## Why

The current Glasslab cluster is:

- Linux-centric
- GPU-worker oriented around NVIDIA
- operationally centered on boring kubeadm workers plus `.44` as the admin host

Making the Macs first-class Kubernetes workers would introduce new complexity at once:

- macOS is not a normal kubeadm worker target
- mixed architecture scheduling becomes part of the cluster story
- model-serving problems get blurred together with cluster-node lifecycle problems

That is the wrong coupling for the immediate goal.

The immediate goal is:

- stronger local inference
- optional separate ranker capacity

Those do not require a Mac to join the cluster.

## Current host split

### `192.168.1.23`

Intended role:

- primary external inference host

### `192.168.1.12`

Intended role:

- secondary inference host
- ranker or reranker host

## What the Macs should host

Good fits:

- Ollama or another reviewed OpenAI-compatible inference endpoint
- a small bounded ranker API
- other sidecar model services that can live behind a stable internal HTTP boundary

Bad fits right now:

- Kubernetes worker membership
- cluster stateful services
- anything that makes Glasslab control plane health depend on macOS node behavior

## Cluster boundary

OpenClaw and `workflow-api` should consume the Macs over explicit internal service URLs.

That keeps the integration point narrow:

- HTTP endpoint
- model name
- validation and rollback path

instead of:

- node bootstrap
- scheduler behavior
- mixed-OS cluster operations

## Practical conclusion

Issue `#32` should be treated as a service-host decision first.

If the Mac path proves stable later, Glasslab can revisit:

- Linux arm64 sidecars
- VM-based worker experiments
- more formal internal inference services

But that should be a later decision, not part of the initial Mac adoption path.
