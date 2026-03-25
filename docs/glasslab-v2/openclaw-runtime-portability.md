# OpenClaw Runtime Portability

This note narrows what issue `#21` really means after the initial runtime export improvements.

## What Improved

The OpenClaw runtime bundle is no longer tied to only one inference topology.

The export path now supports:

- provider base URL override
- default model override
- exported model alias override

That means the generated runtime can target:

- the original in-cluster `vllm` service
- a Mac-hosted external inference endpoint
- another reviewed OpenAI-compatible internal endpoint

without changing the committed provider YAML itself.

## What Is Still `.44`-Special

Even with that improvement, the full operating path is still special to the provisioner.

The current `.44`-local responsibilities are:

- local ignored secret manifests
- canonical `kubectl` admin context
- runtime export and apply flow
- live rollout and validation

Those are different kinds of dependency and should not be blurred together.

## Dependency Split

### Unavoidable Local-Only Material

- secret manifests under `kubeadm/glasslab-v2/secrets/*.local.yaml`
- any local chat-channel credentials or copied tokens

These will remain local-only unless a separate secret-management decision is made.

### Avoidable Runtime Friction

- forcing the runtime bundle to assume one exact inference host
- requiring ad hoc edits to source YAML for every backend change
- making rollback or redeploy harder than necessary

This is the part the current export override work improves.

## Recommended Next Step

The next reduction in `.44` dependence should be boring and narrow.

Do not try to eliminate all provisioner specialness at once.

Instead:

1. keep secrets local-only
2. keep `.44` as the canonical apply host for now
3. make the exported runtime bundle portable across reviewed internal inference backends
4. document the exact export inputs and restart flow clearly

## Practical Export Pattern

Example with the default in-cluster path:

```bash
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
```

Example with an external Mac-hosted inference backend:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://192.168.1.23:11434/v1" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="deepseek-r1:32b" \
GLASSLAB_OPENCLAW_MODEL_ALIAS="glasslab-mac-studio-primary" \
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
```

## Current Scope Boundary

This does not yet solve:

- secret backup
- remote apply from outside `.44`
- disaster recovery for the OpenClaw secret material
- stable operator access routing

Those are separate issues.

This note only narrows the runtime-export part of the problem.
