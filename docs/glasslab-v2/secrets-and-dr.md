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

This is the current backup scope.

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

Current repo-supported backup helper:

- `scripts/backup-glasslab-secrets.sh`
- `scripts/pull-glasslab-secrets-backup.sh`

Recommended operator pattern:

1. run the laptop-side pull helper while on the lab network
2. let it trigger the encrypted backup on `.44`
3. pull the resulting `.tar.gpg` file and manifest back to the laptop
4. keep the decryption passphrase separate from the backup file
5. verify the restore procedure before relying on it

Important:

- `scripts/snapshot-provisioner-config.sh` does not capture ignored secret manifests.
- A Git clone plus `live-config/provisioner/` snapshot is not enough to rebuild v2 secrets.

## Current encrypted backup flow

Preferred path from the operator laptop on the lab network:

```bash
cd /home/gr66ss/cluster-config
./scripts/pull-glasslab-secrets-backup.sh
```

Default local destination on the laptop:

- `/home/gr66ss/glasslab-secret-backups/`

This path does not require inbound access to the laptop. It uses SSH from the laptop to `.44`,
runs the remote encrypted backup helper there, and then pulls the encrypted artifacts back with `scp`.

Lower-level helper on `.44`:

```bash
cd /home/glasslab/cluster-config
./scripts/backup-glasslab-secrets.sh
```

Example with an explicit remote passphrase file when doing a scripted validation run:

```bash
cd /home/gr66ss/cluster-config
./scripts/pull-glasslab-secrets-backup.sh \
  --passphrase-file /tmp/glasslab-secret-passphrase.txt
```

Example with a local staging directory on `.44` first:

```bash
cd /home/glasslab/cluster-config
./scripts/backup-glasslab-secrets.sh \
  --output-dir /home/glasslab/glasslab-secret-backups \
  --copy-dest /mnt/encrypted-backups/glasslab/
```

Default output directory on `.44`:

- `/home/glasslab/glasslab-secret-backups/`

Outputs:

- encrypted archive:
  - `glasslab-secrets-<timestamp>.tar.gpg`
- manifest file:
  - `glasslab-secrets-<timestamp>.manifest.txt`

The manifest records which files were included so the operator can confirm whether:

- only v2 secret manifests were captured
- the related v1 agent-stack secret was also captured

Validated behavior as of 2026-03-19:

- archive creation tested on `.44`
- manifest creation tested on `.44`
- decrypt-and-list of the archive tested on `.44`
- laptop-side pull flow tested end-to-end with:
  - remote encrypted archive creation on `.44`
  - encrypted archive and manifest copied back to the laptop
  - local decrypt-and-list verification of the pulled archive

Chosen normal off-host destination:

- the operator laptop at `/home/gr66ss/glasslab-secret-backups/`

Optional secondary destinations later:

- removable encrypted media
- a separate storage endpoint

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
