# OpenClaw Config

This tree holds the repo-managed source-of-truth for OpenClaw agents, prompts, provider templates, bindings, and policy for Glasslab v2.

It also carries the narrow chat-channel definitions used for first operator-facing validation.

This tree is the committed config source, not the live runtime bundle.

The OpenClaw container does not consume this YAML tree directly. `./scripts/export-openclaw-config.sh` converts it into the native runtime bundle used at deployment time.

Runtime contract:

- source repo path: `services/openclaw-config`
- exported ConfigMap: `glasslab-openclaw-config`
- exported ConfigMap key: `openclaw-runtime.tar.gz`
- in-container runtime root: `/var/lib/openclaw/runtime`
- in-container config path: `/var/lib/openclaw/runtime/openclaw.json`
- in-container workspaces: `/var/lib/openclaw/runtime/workspaces/<agent>/`

Live vs committed:

- committed YAML in this tree is the source of truth for reviewable config
- local secret manifests on `.44` provide live credentials and allowlists
- the exported runtime bundle is the artifact actually mounted into the pod
- the bundle can differ from this tree when local secrets or operator-only settings are applied

Read this tree through three buckets:

- committed intent:
  - prompts, bindings, providers, and policy reviewed in Git
- validated live:
  - whatever the current OpenClaw pod is actually running after export and rollout
- `.44` local only:
  - ignored OpenClaw secret manifest values
  - the currently exported runtime bundle before or after local patching

Default inference path:

- the committed default provider source is now `providers/local-ollama-native.yaml`
- the default interactive chat model is `.12` native Ollama:
  - `glasslab-ollama/qwen3:14b`
- the legacy vLLM provider remains in the repo only as an explicit override / fallback path

First channel notes:

- the first validated chat front door is WhatsApp
- the committed channel config keeps validation in direct-message self-chat mode only
- the channel is exported only when `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml` defines `OPENCLAW_WHATSAPP_OWNER`
- the exporter also pre-enables the bundled `whatsapp` plugin so channel login does not rely on runtime config writes
- the exported runtime pins WhatsApp to `channels.whatsapp.accounts.default.authDir=/var/lib/openclaw/state/credentials/whatsapp/default`
- no broad allowlist or group routing is enabled in repo config

Use `./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply` to inspect the generated runtime tree before applying it to the cluster.

When debugging drift, always compare all three:

1. this committed YAML tree
2. the freshly exported runtime bundle
3. the live `/var/lib/openclaw/runtime/openclaw.json` inside the pod

Maintainer note:

- keep the OpenClaw surface session-first
- treat the first operator invocation as a session bootstrap or session recovery step before workflow-family selection
- if the required session state is missing, the operator should name the missing prerequisite and give one concrete next step instead of chaining recovery attempts
- use skills as bounded capability calls that mutate a session in controlled steps
- treat workflow families as execution templates selected after the session state is ready
- do not let prompt wording imply that workflow families are the main product object
