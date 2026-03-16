# Secrets And DR

Glasslab v2 intentionally keeps live secret values out of Git. That makes the repo safe to share, but it also means secret durability must be handled separately.

## Current secret locations

V2 local secret manifests on `.44`:

- `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml`
- `kubeadm/glasslab-v2/secrets/20-minio.local.yaml`
- `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`

Related v1 secret manifest still used by the local vLLM path:

- `kubeadm/agent-stack/12-agent-secrets.yaml`

These files are ignored by Git.

## What is intentionally not committed

- Postgres credentials
- MinIO root credentials
- OpenClaw gateway token
- OpenClaw copy of the vLLM API key
- v1 agent stack and vLLM secret values

## Minimum backup expectations

- Keep an encrypted off-host backup of the local secret manifests from `.44`.
- Store that backup separately from the Git remote.
- Keep file permissions restrictive on `.44` and on the backup copy.
- Record the restore location and procedure in operator docs, not in shell history only.

Important:

- `scripts/snapshot-provisioner-config.sh` does not capture ignored secret manifests.
- A Git clone plus `live-config/provisioner/` snapshot is not enough to rebuild v2 secrets.

## Rotation expectations

Rotate these values after any suspected leak or after rebuilding `.44` from scratch:

- `POSTGRES_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_VLLM_API_KEY` if it was copied from the v1 secret and the upstream value changed

Also rotate any v1 secret that v2 currently depends on, such as the vLLM API key in `glasslab-agent-secrets`.

## High-level restore path

1. Restore the local secret manifests onto `.44`.
2. Re-apply the secret manifests to the cluster.
3. Restart workloads that consume those values.
4. Re-run the v2 smoke test and OpenClaw health check.
5. If the original values are unavailable, generate new values and rotate the affected services instead of trying to reconstruct old tokens.

Use `docs/glasslab-v2/runbooks/restore-v2-secrets.md` for the concrete restore sequence.
