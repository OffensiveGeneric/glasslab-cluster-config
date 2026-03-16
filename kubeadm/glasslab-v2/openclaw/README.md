# OpenClaw

This directory holds the internal-only OpenClaw deployment manifests for Glasslab v2.

The repo-managed source config under `services/openclaw-config` is exported into a native OpenClaw runtime bundle by `scripts/export-openclaw-config.sh` before the deployment is applied.

Runtime contract:

- ConfigMap name: `glasslab-openclaw-config`
- ConfigMap key: `openclaw-runtime.tar.gz`
- init-container mount: `/config-archive/openclaw-runtime.tar.gz`
- unpacked runtime root: `/var/lib/openclaw/runtime`
- native config file: `/var/lib/openclaw/runtime/openclaw.json`
- agent workspaces: `/var/lib/openclaw/runtime/workspaces/<agent>/`
- service port: `18789`

Required local secret manifest:

- `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`

Channel notes:

- the first validated chat channel is WhatsApp
- enabling it requires `OPENCLAW_WHATSAPP_OWNER` in `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`
- linked WhatsApp credentials are written under `/var/lib/openclaw/state/credentials/whatsapp/default/`
- the current Deployment keeps `/var/lib/openclaw/state` on `emptyDir`, so WhatsApp login state is not durable yet
