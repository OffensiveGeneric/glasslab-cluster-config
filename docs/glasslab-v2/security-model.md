# Security Model

Glasslab v2 should assume unattended components will eventually run without a human watching every prompt. The default posture therefore stays restrictive.

## Internal-only access

- keep `workflow-api`, Postgres, NATS, MinIO, and OpenClaw as `ClusterIP` services
- do not create public ingress by default
- access OpenClaw through the internal network, port-forwarding, a tunnel, or Tailscale
- require token authentication for the OpenClaw HTTP surface

## Sandboxing requirements

- OpenClaw agents should run with a restricted service account and no cluster-admin privileges
- do not mount host paths into OpenClaw pods
- keep writable filesystem scope limited to explicit workspace or cache paths
- do not allow agent-driven arbitrary shell execution inside the cluster by default

## Restricted tools

Default-deny the following until a reviewed need exists:

- `kubectl apply`, `patch`, `delete`, and equivalent mutating cluster actions
- arbitrary shell commands
- arbitrary outbound HTTP requests
- Git push or force-reset operations
- execution of unapproved workflow families

## Approval tiers

- `tier-1-read-only`: summaries, literature digestion, and status checks
- `tier-2-approved-execution`: reviewed workflows using approved models, runner images, and resource profiles
- `tier-3-human-approval`: infrastructure changes, new workflows, approval-scope changes, or anything that escapes bounded execution
