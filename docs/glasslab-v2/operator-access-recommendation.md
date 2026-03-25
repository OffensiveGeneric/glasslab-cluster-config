# Operator Access Recommendation

This note makes a concrete recommendation for issue `#34`.

The question is not whether Glasslab should build a broad ingress layer.

The question is how operators should reach the one human-facing surface that actually matters without widening the trust boundary around the rest of the stack.

## Recommendation

Adopt a narrow operator-only access path for OpenClaw first.

Prefer:

- authenticated tailnet or VPN-style operator access
- OpenClaw as the only first-class remotely reachable operator surface
- backend services remaining `ClusterIP` only

Do not start with:

- broad internal ingress
- exposing multiple backend services at once
- direct outside-user access to workflow internals

## Why This Is The Better First Move

### 1. It Matches The Product Shape

OpenClaw is the operator shell.

`workflow-api`, Postgres, NATS, and MinIO are backend internals. They should not become operator entrypoints just because the cluster needs one stable access path.

### 2. It Keeps The Trust Boundary Small

If Glasslab exposes only OpenClaw through an authenticated operator lane:

- there is one service to harden first
- one authentication story to document
- one place to audit operator actions

That is much easier to defend than exposing a bundle of cluster services.

### 3. It Aligns With The Current Deployment Reality

The repo already assumes:

- backend services stay internal
- day-to-day admin still uses `kubectl port-forward` where needed
- OpenClaw is the narrow front door

So the recommended access path should preserve that instead of introducing a broader ingress pattern too early.

## Proposed Near-Term Shape

### Operator Surface

- expose OpenClaw only
- keep it authenticated
- keep all other v2 services private

### Admin Surface

- continue using `kubectl port-forward` for backend diagnostics
- continue using bastion or provisioner access for cluster admin tasks

### Later Optional Surfaces

Add only if there is a reviewed operator need:

- MinIO console
- MLflow UI

Those should not automatically piggyback on the first OpenClaw access decision.

## Tailscale Or Reverse Proxy?

If the goal is a small number of approved operator devices, prefer the Tailscale-style path first.

Why:

- operator identity is clearer
- the exposure scope is smaller
- it avoids turning the lab LAN itself into the main trust boundary

Use a reverse proxy instead only if the organization already has a stronger internal auth/TLS pattern there and wants one boring internal URL without introducing another operator access system.

## What This Means For The Repo

The next operational work should be:

1. pick the host that terminates the operator path
2. document the auth model
3. document OpenClaw as the only exposed operator route
4. keep backend service manifests unchanged as `ClusterIP`

## Non-Goals

This recommendation does not imply:

- general ingress for all v2 services
- outside-researcher self-service access
- direct exposure of `workflow-api`
- a promise that the WhatsApp path replaces operator authentication

## Bottom Line

Glasslab should add one stable authenticated path to OpenClaw.

Everything else should stay private until there is a stronger reason to widen the access model.

## References

- `operator-access-options.md`
- `internal-service-exposure.md`
- `openclaw-gateway.md`
