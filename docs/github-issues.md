# GitHub Issue Drafts

This file is a staging area for real GitHub issues.

Use it when:

- `gh` is not available
- you are drafting from home
- you want a clean backlog before creating issues on the canonical machine

## Suggested Labels

- `area:infra`
- `area:pxe`
- `area:k8s`
- `area:gpu`
- `area:v1-agent-stack`
- `area:v2-core`
- `area:workflow-api`
- `area:workflow-registry`
- `area:openclaw`
- `area:vllm`
- `area:storage`
- `area:security`
- `area:docs`
- `state:blocked`
- `state:needs-lab-access`
- `state:needs-live-validation`
- `state:design`
- `state:ready`

## Suggested Milestones

- `Stabilize v2 core`
- `Durable storage`
- `OpenClaw operator hardening`
- `Chat channel validation`
- `Provisioner hardening`
- `Repo clarity`

## Epic 1

Title:

`Epic: Revalidate actual live Glasslab state from .44`

Labels:

- `area:infra`
- `area:v2-core`
- `area:docs`
- `state:needs-lab-access`
- `state:needs-live-validation`

Body:

```md
## Goal

Reconcile actual live cluster state on `.44` with the current committed repo and docs.

## Why

The laptop can only see GitHub while off-site. Operational truth still lives on `.44`, including ignored secrets, exported runtime bundles, imported images, and any unpushed work. We need a fresh baseline before making further platform decisions.

## Tasks

- [ ] Check cluster node and pod state from `.44`
- [ ] Check `glasslab-agents` pod, service, and job state
- [ ] Check `glasslab-v2` pod, service, and deployment state
- [ ] Confirm OpenClaw live replica count and runtime status
- [ ] Confirm vLLM pod health and service reachability
- [ ] Confirm GPU allocatable state on `node01`, `node02`, and `node04`
- [ ] Record repo-vs-live drift in docs

## Done When

- a single doc update captures the actual current live state
- the next session no longer has to guess what is live versus merely committed
```

## Epic 2

Title:

`Epic: Add durable storage for Glasslab v2 core services`

Labels:

- `area:v2-core`
- `area:storage`
- `area:k8s`
- `state:needs-lab-access`

Body:

```md
## Goal

Replace fragile `emptyDir` assumptions for the stateful `glasslab-v2` services with explicit durable storage.

## Why

`workflow-api` can tolerate statelessness better than `Postgres`, `MinIO`, and `NATS`. Right now the platform direction is ahead of the storage primitives.

## Tasks

- [ ] Decide the first durable storage approach for v2
- [ ] Implement explicit storage for `Postgres`
- [ ] Implement explicit storage for `MinIO`
- [ ] Revisit `NATS` durability expectations
- [ ] Document which services are durable versus still ephemeral
- [ ] Update runbooks and manifests to match reality

## Done When

- the important v2 stateful services no longer depend on `emptyDir`
- operators can explain the storage posture without caveats or guesswork
```

## Epic 3

Title:

`Epic: Reduce dependence on .44-local image import and runtime state`

Labels:

- `area:v2-core`
- `area:infra`
- `area:storage`
- `state:design`

Body:

```md
## Goal

Reduce the number of deployment paths that only work because `.44` builds images, exports runtime bundles, or imports images into node-local containerd.

## Why

The repo looks more portable than the actual operational path. This increases hidden coupling and makes failover or rescheduling harder.

## Tasks

- [ ] Inventory current custom images that still depend on local import
- [ ] Decide on a pullable registry or mirror path
- [ ] Remove node pinning that exists only because of manual image import
- [ ] Document remaining `.44`-only runtime materialization steps

## Done When

- critical services can be deployed without hidden manual import dependencies
```

## Epic 4

Title:

`Epic: Harden OpenClaw as a narrow operator gateway`

Labels:

- `area:openclaw`
- `area:vllm`
- `area:v2-core`
- `state:needs-lab-access`

Body:

```md
## Goal

Keep OpenClaw useful as the human-facing gateway without widening its trust boundary or pretending the local tool-calling path is more reliable than it is.

## Why

The current safe pattern is narrow and mostly no-arg. That is good. The next work should make it more repeatable, not more magical.

## Tasks

- [ ] Re-run the no-arg validation lifecycle from `.44`
- [ ] Keep the operator tool surface intentionally small
- [ ] Confirm runtime export and restart flow is repeatable
- [ ] Decide how to track experimental argumented tools separately from safe defaults
- [ ] Document the current approved operator path clearly

## Done When

- the safe OpenClaw path is easy to explain and easy to revalidate
```

## Epic 5

Title:

`Epic: Purge remaining password-era provisioner and PXE debt`

Labels:

- `area:pxe`
- `area:security`
- `area:infra`
- `state:needs-lab-access`

Body:

```md
## Goal

Remove remaining historical password material and password-era helper assumptions from the tracked provisioner and PXE/autoinstall path.

## Why

The live nodes were hardened, but tracked snapshots and some helper flows still reflect earlier debug-era assumptions.

## Tasks

- [ ] Identify current helper scripts that still assume node sudo passwords
- [ ] Remove those assumptions where practical
- [ ] Purge unnecessary password material from tracked PXE/autoinstall config
- [ ] Revalidate provisioning behavior after cleanup

## Done When

- tracked provisioning config no longer carries avoidable password debt
- helper flows match the hardened SSH posture
```

## Issue 1

Title:

`Document repo state vs documented live state vs actual live state`

Labels:

- `area:docs`
- `state:ready`

Body:

```md
## Goal

Make the three-truth model explicit in the repo so off-site work does not accidentally get described as live-validated.

## Tasks

- [ ] Keep the operator orientation doc current
- [ ] Reference the distinction from the root README
- [ ] Add the distinction to any future operational summary docs where needed
```

## Issue 2

Title:

`Create a single live-state report after the next in-lab validation`

Labels:

- `area:docs`
- `state:needs-lab-access`
- `state:needs-live-validation`

Body:

```md
## Goal

Produce one current live-state report after checking the cluster from `.44`.

## Why

Right now live facts are spread across older handoff notes and newer architecture docs.

## Tasks

- [ ] Check actual cluster state from `.44`
- [ ] Record what is live, what is degraded, and what is only designed
- [ ] Link the report from the root README or operator orientation doc
```

## Issue 3

Title:

`Add durable static PV/PVC wiring for Glasslab v2 Postgres`

Labels:

- `area:storage`
- `area:v2-core`
- `state:needs-lab-access`

Body:

```md
## Goal

Move `glasslab-v2` Postgres off `emptyDir` and onto explicit durable storage.

## Tasks

- [ ] Choose the host path and node placement
- [ ] Add the storage manifest or PVC wiring
- [ ] Update the Postgres manifest
- [ ] Verify restart behavior and data retention
```

## Issue 4

Title:

`Add durable static PV/PVC wiring for Glasslab v2 MinIO`

Labels:

- `area:storage`
- `area:v2-core`
- `state:needs-lab-access`

Body:

```md
## Goal

Move `glasslab-v2` MinIO off `emptyDir` and onto explicit durable storage.

## Tasks

- [ ] Choose the host path and node placement
- [ ] Add the storage manifest or PVC wiring
- [ ] Update the MinIO manifest
- [ ] Verify restart behavior and object retention
```

## Issue 5

Title:

`Back up ignored .44-local secret manifests with an encrypted off-host process`

Labels:

- `area:security`
- `area:v2-core`
- `state:design`
- `state:needs-lab-access`

Body:

```md
## Goal

Create a repeatable encrypted backup path for ignored secret manifests that currently live only on `.44`.

## Tasks

- [ ] Define which local secret files are in scope
- [ ] Choose an encrypted backup mechanism
- [ ] Document the backup and restore process
- [ ] Test the process without exposing plaintext secrets in Git
```

## Issue 6

Title:

`Publish or mirror custom workflow-api images instead of relying on node-local import`

Labels:

- `area:v2-core`
- `area:infra`
- `state:design`

Body:

```md
## Goal

Stop depending on `.44` plus `ctr import` as the only practical deployment path for custom service images.

## Tasks

- [ ] Document the current local import workflow clearly
- [ ] Choose the target registry or mirror approach
- [ ] Update image references and deployment steps
- [ ] Remove pinning caused only by manual image placement
```

## Issue 7

Title:

`Re-run OpenClaw no-arg tool-calling validation and capture results`

Labels:

- `area:openclaw`
- `area:vllm`
- `state:needs-lab-access`
- `state:needs-live-validation`

Body:

```md
## Goal

Revalidate the currently safe no-arg OpenClaw workflow-api tool path on the live cluster.

## Tasks

- [ ] Run the create-validation-run path
- [ ] Run the get-last-validation-run path
- [ ] Capture backend proof from `workflow-api` logs
- [ ] Update the tool-calling reliability doc if results changed
```

## Issue 8

Title:

`Track experimental argumented tools separately from safe OpenClaw defaults`

Labels:

- `area:openclaw`
- `state:design`

Body:

```md
## Goal

Keep the safe operator path stable while making it explicit which tools are experimental.

## Tasks

- [ ] Decide how experimental tools should be labeled or isolated
- [ ] Keep state-changing defaults on the known-good no-arg path
- [ ] Update docs so operators do not confuse experimental reads with production-safe actions
```

## Issue 9

Title:

`Replace remaining password-dependent maintenance helpers`

Labels:

- `area:pxe`
- `area:security`
- `state:needs-lab-access`

Body:

```md
## Goal

Remove helper behavior that still assumes password-era node access.

## Tasks

- [ ] Identify scripts that still expect password-based sudo or SSH paths
- [ ] Update them to fit the hardened key-only node model
- [ ] Verify the replacement flow from `.44`
```

## Issue 10

Title:

`Create a top-level decision log for major Glasslab architecture choices`

Labels:

- `area:docs`
- `state:ready`

Body:

```md
## Goal

Reduce re-litigation and memory loss by recording major architectural decisions in one place.

## Candidate decisions

- why `v2` exists separately from the Titanic stack
- why OpenClaw is the gateway and not the workflow brain
- why the current safe operator path favors no-arg tools
- why durable storage and image distribution are the next priorities
```
