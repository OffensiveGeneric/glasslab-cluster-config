# Image Distribution

Glasslab v2 currently mixes pull-based upstream images with one manual import path for the custom backend.

## Current state

- `workflow-api` uses `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.0`.
- The repo currently builds that image on `.44` with `scripts/build-import-workflow-api-image.sh`.
- The script saves a tarball, copies it to `node03`, and imports it into `containerd` with `ctr -n k8s.io images import`.
- The committed `workflow-api` Deployment is pinned to `node03`.
- Postgres, NATS, MinIO, and OpenClaw currently pull their images directly.

## Why node03 pinning exists

- The custom `workflow-api` image is not yet guaranteed to be pullable by every node.
- Pinning the Deployment to `node03` keeps the first live path deterministic because the image was imported there directly.
- This is a valid bring-up compromise, not a steady-state design.

## Risks of the current path

- A reschedule away from `node03` will fail unless the image is imported on the new node too.
- Manual import is easy to forget after image rebuilds.
- Rollback and disaster recovery depend on operator memory instead of a pullable artifact.
- The current pattern does not scale to multiple custom v2 workloads.

## Recommended future strategy

1. Publish custom Glasslab images to a pullable registry.
2. Pin operator-managed images to explicit tags and then to digests once the release flow is stable.
3. Remove `node03` pinning after at least one non-`node03` worker can pull and start the image successfully.
4. Optionally add an internal registry mirror if the lab needs faster pulls or less dependence on public registry availability.

## Migration path

1. Build the image on `.44` as today.
2. Push it to the chosen registry instead of stopping at `ctr import`.
3. Update the Deployment to use the pushed image tag or digest.
4. Validate that multiple nodes can pull it.
5. Remove the `nodeSelector` from `kubeadm/glasslab-v2/workflow-api/20-deployment.yaml`.
6. Retire the manual import step from the primary runbook.

## Operator note

Until that migration happens, treat the following as a hard current limitation:

- `workflow-api` is tied to `node03`
- image rebuilds require a fresh import on `node03`
- disaster recovery must include the custom image workflow, not just manifests
