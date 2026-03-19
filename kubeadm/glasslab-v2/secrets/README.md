# Secrets

Store non-committed local v2 secret manifests here.

Recommended local files:
- `10-postgres.local.yaml`
- `20-minio.local.yaml`
- `30-openclaw.local.yaml`

Related non-v2 secret file still relevant to the live stack:

- `../../agent-stack/12-agent-secrets.yaml`

Recommended OpenClaw secret keys:
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_VLLM_API_KEY`
- `OPENCLAW_WHATSAPP_OWNER` when the WhatsApp path is enabled

These files are ignored by Git and should be applied from the provisioner only.

Encrypted off-host backups should be created with:

- `scripts/backup-glasslab-secrets.sh`
