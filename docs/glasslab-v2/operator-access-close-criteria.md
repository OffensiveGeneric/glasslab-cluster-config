# Operator Access Close Criteria

This note narrows issue `#34`.

The key decision is mostly already made:

- backend internals stay private
- OpenClaw is the first and only operator-facing service that should get a stable authenticated route
- the preferred first access model is a Tailscale/VPN-style operator lane unless a stronger existing reverse-proxy/auth path already exists

What remained unclear was what should count as enough progress to consider the issue materially resolved.

## Close Criteria

Issue `#34` should be considered closeable when these are true:

1. the repo explicitly records OpenClaw as the only first-class operator-facing service
2. backend services remain documented as private `ClusterIP` internals
3. one preferred access pattern is documented
4. the remaining work is implementation-specific rather than architectural

## Current Status Against Those Criteria

### 1. OpenClaw as the first operator surface

Satisfied.

References:

- `operator-access-recommendation.md`
- `openclaw-gateway.md`

### 2. Backend internals remain private

Satisfied.

References:

- `operator-access-options.md`
- `internal-service-exposure.md`

### 3. Preferred access pattern documented

Satisfied.

Current recommendation:

- authenticated tailnet / VPN-style operator path first
- reverse proxy only if there is a stronger existing internal auth/TLS pattern

### 4. Remaining work is implementation-specific

Satisfied.

The remaining open questions are now things like:

- which host terminates the operator route
- which auth system is actually used
- what exact runbook or manifest config is applied

Those are implementation details, not unresolved architecture.

## What Should Not Keep This Issue Open

Do not keep this issue open merely because:

- the final Tailscale or reverse-proxy implementation has not been deployed yet
- WhatsApp is still being revalidated
- MinIO console or MLflow might later need their own operator path

Those are separate rollout or later-scope questions.

## Bottom Line

The decision issue is effectively answered.

The remaining work belongs in implementation or deployment issues, not in the abstract access-choice issue.

## References

- `operator-access-options.md`
- `operator-access-recommendation.md`
- `remote-admin-path.md`
