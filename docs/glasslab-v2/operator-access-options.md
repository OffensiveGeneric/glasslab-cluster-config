# Operator Access Options

This note narrows the realistic steady-state access patterns for Glasslab operator-facing services.

It exists to turn the broad question in issue `#34` into a smaller decision.

## Decision Frame

The project does not need a general ingress strategy for all v2 services.

It needs a stable authenticated access path only for a small set of human-facing surfaces.

Everything else should stay private to the cluster.

## What Should Stay Private

Keep these as `ClusterIP`-only services:

- `glasslab-workflow-api`
- `glasslab-postgres`
- `glasslab-nats`
- MinIO API on `glasslab-minio:9000`

These are backend or storage internals, not operator entrypoints.

## Which Services Deserve Stable Operator Access

The likely operator-facing candidates are:

- OpenClaw
- MinIO console on `glasslab-minio:9001`
- optional MLflow UI if it is enabled later

OpenClaw is the strongest first candidate because it is already the intended operator gateway.

## Realistic Options

### 1. Keep Port-Forward As The Only Path

Good:

- simplest
- no new routing infrastructure
- low accidental exposure risk

Bad:

- poor steady-state operator UX
- brittle for repeat use
- does not create a stable internal URL for the one service that likely wants it

Use this for:

- bring-up
- debugging
- validation

Do not treat this as the long-term default if OpenClaw becomes a real day-to-day operator surface.

### 2. Internal Reverse Proxy In Front Of OpenClaw

Good:

- keeps the exposure surface narrow
- can enforce auth centrally
- fits a “human-facing services only” rule

Bad:

- adds cluster or provisioner-side proxy config to maintain
- still needs a clear internal network and TLS story

This is a good fit if Glasslab wants one boring internal URL for OpenClaw without widening the exposure model.

### 3. Tailscale-Served Route For OpenClaw

Good:

- strong operator identity model
- avoids broad LAN exposure
- simple fit for a small number of trusted operators

Bad:

- introduces a dependency on Tailscale enrollment and device posture
- still needs a decision about where the served route actually runs

This is a strong candidate if the real goal is “reachable from approved operator devices” rather than “discoverable on the whole lab LAN.”

### 4. Broad Internal Ingress For Multiple Services

Good:

- centralizes routing

Bad:

- too much machinery for the current scope
- encourages exposing more than Glasslab actually needs
- blurs the trust boundary between backend internals and human-facing surfaces

Do not make this the first move.

## Recommended Near-Term Choice

Use this sequence:

1. keep port-forward for backend admin and smoke-test paths
2. choose one stable authenticated access path for OpenClaw only
3. expand to MinIO console or MLflow later only if there is a reviewed operator need

The real decision is therefore not “should Glasslab add ingress?”

It is:

- Tailscale-served authenticated OpenClaw route
- or internal authenticated reverse proxy for OpenClaw

## What This Means For The Repo

If the next step is Tailscale:

- add a design note or runbook for where the served route lives
- keep OpenClaw itself as `ClusterIP`
- document operator auth expectations

If the next step is reverse proxy:

- add one narrow proxy manifest or host-side config path for OpenClaw only
- keep backend internals out of that route
- document auth and TLS expectations explicitly
