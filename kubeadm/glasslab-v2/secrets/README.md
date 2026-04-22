# Secrets

Store non-committed local v2 secret manifests here.

Recommended local files:
- `10-postgres.local.yaml`
- `15-workflow-api.local.yaml`
- `20-minio.local.yaml`

Related non-v2 secret file still relevant to the live stack:

- `../../agent-stack/12-agent-secrets.yaml`

Recommended WhatsApp gateway local secret keys:
- `WHATSAPP_OWNER`
- `WHATSAPP_ALLOW_FROM`

These files are ignored by Git and should be applied from the provisioner only.

Encrypted off-host backups should be created with:

- `scripts/backup-glasslab-secrets.sh`
