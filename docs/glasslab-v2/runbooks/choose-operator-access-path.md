# Choose Operator Access Path

This runbook exists to make issue `#34` actionable.

Its purpose is not to expose more services.

Its purpose is to choose one stable authenticated path for operator-facing access when port-forward is no longer enough.

## Scope

Treat only these as candidates for stable operator-facing access:

- OpenClaw
- MinIO console
- optional MLflow UI

Keep these private to the cluster:

- `glasslab-workflow-api`
- `glasslab-postgres`
- `glasslab-nats`
- MinIO API

## Default Until A Choice Is Made

Use `kubectl port-forward` for:

- smoke tests
- validation
- short-lived admin access

Do not invent a broad ingress posture while the decision is still unsettled.

## Choose The First Stable Target

The first stable operator-facing target should be:

- OpenClaw

Reason:

- it is already the intended operator gateway
- exposing backend APIs directly would widen the trust boundary unnecessarily

## Compare The Two Real Candidates

### Option A: Tailscale-Served OpenClaw Route

Choose this if:

- operator identity should be tied to approved devices and users
- the desired reachability is “trusted operator devices” rather than general lab-LAN discoverability
- you want to avoid adding a more general cluster ingress posture first

Questions to answer:

- where does the served route terminate?
- which device or host owns the Tailscale route?
- how is the OpenClaw token managed alongside Tailscale identity?

### Option B: Internal Reverse Proxy For OpenClaw

Choose this if:

- you want one boring internal DNS name on the lab network
- the operator audience is entirely on the internal network
- cluster or provisioner-side proxy management is acceptable

Questions to answer:

- where does the reverse proxy live?
- what internal DNS name is used?
- what auth and TLS posture is required?

## Decision Checklist

Before declaring a choice, answer all of these:

1. Which single service is being exposed first?
2. Who are the operators that need access?
3. Is reachability device-identity-based or network-location-based?
4. What auth protects the HTTP surface?
5. Does the chosen path keep backend internals private?
6. Can the path be explained in one short operator runbook?

## Repo Follow-Through

If you choose Tailscale:

- add one note or runbook for where the served route runs
- keep OpenClaw as `ClusterIP`
- do not add general ingress manifests as a substitute

If you choose reverse proxy:

- add one narrow example or real config for OpenClaw only
- keep the ingress placeholder examples scoped to operator-facing services

## Success Condition

This work is done when:

- one stable authenticated access path exists for OpenClaw
- the chosen path is documented clearly
- no additional backend internals were exposed to get there
