# Secrets

Store non-committed local v2 secret manifests here.

Recommended local files:
- `10-postgres.local.yaml`
- `20-minio.local.yaml`
- `30-openclaw.local.yaml` when OpenClaw is brought up later

Recommended OpenClaw secret keys:
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_VLLM_API_KEY`

These files are ignored by Git and should be applied from the provisioner only.
