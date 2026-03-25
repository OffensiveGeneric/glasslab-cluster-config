# Switch OpenClaw Inference Backend

This runbook exists to make issue `#21` operationally boring.

It assumes:

- `.44` remains the canonical apply host
- secrets remain local-only on `.44`
- the OpenClaw runtime bundle is exported on `.44`

## Purpose

Switch OpenClaw between reviewed internal inference backends without editing the committed provider YAML each time.

Examples:

- default in-cluster `vllm`
- external Mac-hosted Ollama or other OpenAI-compatible endpoint

## 1. Log Into The Provisioner

```bash
ssh glasslab@192.168.1.44
cd /home/glasslab/cluster-config
```

## 2. Confirm The Backend You Intend To Use

Always confirm:

- the backend URL is reachable from the network path OpenClaw will use
- the model is actually present on that backend
- the backend is reviewed and intentional

Default in-cluster example:

```bash
kubectl -n glasslab-agents get svc vllm
```

External Mac-hosted example:

```bash
curl http://192.168.1.23:11434/api/tags
curl http://192.168.1.23:11434/v1/models
```

## 3. Export The Runtime Bundle For The Intended Backend

Default in-cluster path:

```bash
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
```

External backend path:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://192.168.1.23:11434/v1" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="deepseek-r1:32b" \
GLASSLAB_OPENCLAW_MODEL_ALIAS="glasslab-mac-studio-primary" \
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
```

## 4. Inspect The Exported Bundle

Confirm:

- `/tmp/openclaw-runtime/openclaw.json` exists
- the `workflow-api` URL is correct
- the provider base URL is the intended backend
- the default model is the intended model

Example:

```bash
python3 -m json.tool /tmp/openclaw-runtime/openclaw.json | sed -n '1,240p'
sed -n '1,120p' /tmp/openclaw-runtime/RUNTIME-CONTRACT.md
```

## 5. Apply The Runtime Bundle

For the default path:

```bash
./scripts/export-openclaw-config.sh
```

For an overridden path, re-run the same command with the same overrides and without `--no-apply`:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://192.168.1.23:11434/v1" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="deepseek-r1:32b" \
GLASSLAB_OPENCLAW_MODEL_ALIAS="glasslab-mac-studio-primary" \
./scripts/export-openclaw-config.sh
```

## 6. Restart OpenClaw If It Is Live

If OpenClaw is already scaled up:

```bash
kubectl -n glasslab-v2 rollout restart deploy/glasslab-openclaw
kubectl -n glasslab-v2 rollout status deploy/glasslab-openclaw --timeout=300s
```

If OpenClaw is scaled down, keep it down until you are ready to validate.

## 7. Validate The New Backend

If OpenClaw is scaled up:

```bash
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200
kubectl -n glasslab-v2 port-forward svc/glasslab-openclaw 18789:18789
```

Then perform the normal operator validation flow and, if relevant, the tool-calling harness:

```bash
./scripts/check-openclaw-tool-calling.sh --attempts 5
```

## 8. Roll Back If Needed

Return to the last known-good backend by re-exporting the runtime bundle with the prior backend inputs and restarting OpenClaw again.

## Notes

- this runbook reduces runtime-bundle friction, not secret-management friction
- it does not make `.44` optional
- it does not replace live validation from `.44`
