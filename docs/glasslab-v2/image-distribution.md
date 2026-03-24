# Image Distribution

Glasslab v2 currently mixes pull-based upstream images with private GHCR paths for the custom backend and runner images.

## Current state

- `workflow-api` uses `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.9`.
- `generic-tabular-benchmark` runs use `ghcr.io/offensivegeneric/glasslab-tabular-runner:0.1.1`.
- `literature-to-experiment` runs use `ghcr.io/offensivegeneric/glasslab-literature-runner:0.1.1`.
- The first real execution path now depends on both images being pullable from private GHCR.
- The steady-state path is now:
  - build and push `workflow-api` with `scripts/push-workflow-api-image.sh`
  - build and push the tabular runner with `scripts/push-tabular-runner-image.sh`
  - create or refresh the in-cluster pull secret with `scripts/create-ghcr-pull-secret.sh`
  - let Kubernetes pull the image on whichever worker schedules the pod
- live validation on 2026-03-23 confirmed the deployment could pull and run on `node05` instead of `node03`
- The old `.44` import helper still exists as an emergency fallback, not the primary deployment path.
- Postgres, NATS, MinIO, and OpenClaw currently pull their images directly.

## Why node03 pinning existed

- The first live path predated any cluster pull secret.
- Importing directly into `node03` containerd kept the initial bring-up deterministic.
- That was a valid bring-up compromise, not a steady-state design.

## Why the private GHCR path is better

- A reschedule no longer depends on node-local image import.
- Rollback and disaster recovery can use a pullable artifact instead of remembered `ctr import` steps.
- The same pattern can be reused for other private Glasslab images.
- The cluster only needs read access to the package, not full GitHub repo access.

## Current private-registry strategy

1. Build and push `workflow-api` and the runner images to private GHCR.
2. Maintain a `glasslab-ghcr-pull` Docker registry secret in the `glasslab-v2` namespace.
3. Pin operator-managed images to explicit tags and then to digests once the release flow is stable.
4. Keep the old import helper only as a break-glass fallback.
5. Optionally add an internal registry mirror later if the lab wants faster pulls or less dependence on GitHub availability.

## Migration path

1. Log Docker into `ghcr.io` with a GitHub token that can write packages.
2. Push `workflow-api` with `scripts/push-workflow-api-image.sh` and the runner with `scripts/push-tabular-runner-image.sh`.
3. Create or refresh the pull secret with `scripts/create-ghcr-pull-secret.sh`.
4. Update the Deployment to use the pushed image tag or digest.
5. Validate that at least one non-`node03` worker can pull and start the image.
6. Retire the manual import step from the primary runbook.

## Operator note

Current assumptions:

- the cluster needs a valid `glasslab-ghcr-pull` secret in `glasslab-v2`
- image rebuilds should produce a new GHCR tag before rollout
- the old import helper remains available if GHCR is temporarily unavailable or credentials need recovery
