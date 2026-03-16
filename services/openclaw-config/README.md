# OpenClaw Config

This tree holds the repo-managed source-of-truth for OpenClaw agents, prompts, provider templates, bindings, and policy for Glasslab v2.

It also carries the narrow chat-channel definitions used for first operator-facing validation.

The OpenClaw container does not consume this YAML tree directly. `./scripts/export-openclaw-config.sh` converts it into the native runtime bundle used at deployment time.

Runtime contract:

- source repo path: `services/openclaw-config`
- exported ConfigMap: `glasslab-openclaw-config`
- exported ConfigMap key: `openclaw-runtime.tar.gz`
- in-container runtime root: `/var/lib/openclaw/runtime`
- in-container config path: `/var/lib/openclaw/runtime/openclaw.json`
- in-container workspaces: `/var/lib/openclaw/runtime/workspaces/<agent>/`

First channel notes:

- the first validated chat front door is WhatsApp
- the committed channel config keeps validation in direct-message self-chat mode only
- the channel is exported only when `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml` defines `OPENCLAW_WHATSAPP_OWNER`
- no broad allowlist or group routing is enabled in repo config

Use `./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply` to inspect the generated runtime tree before applying it to the cluster.
