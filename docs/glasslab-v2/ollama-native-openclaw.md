# Ollama Native OpenClaw Path

This note records the 2026-03-24 finding that mattered most after the Mac cutover:

- remote Ollama with OpenClaw should use the native Ollama API
- not the OpenAI-compatible `/v1` path

## What Was Going Wrong

The first Mac cutover pointed OpenClaw at:

- `http://192.168.1.23:11434/v1`

and exported the provider as:

- `api: "openai-completions"`

That was enough for plain chat inference, but it was the wrong integration mode for tool calling.

The live harness failure after the cutover was:

- `400 registry.ollama.ai/library/deepseek-r1:32b does not support tools`

That failure came from the current OpenClaw + Ollama integration path, not from plain chat generation.

## What OpenClaw's Current Provider Docs Say

The current official OpenClaw Ollama provider docs say:

- OpenClaw integrates with Ollama's native API at `/api/chat`
- remote Ollama users should not use the `/v1` OpenAI-compatible URL when they depend on tool calling
- native provider config should use:
  - `baseUrl: "http://host:11434"`
  - `api: "ollama"`

Operationally, that means:

- `/v1` is acceptable for plain OpenAI-format compatibility
- `/v1` is the wrong default when the goal is native OpenClaw tool behavior

## What Was Validated Live

Validated on `2026-03-24`:

- `.12` `qwen3:14b` successfully returned a native Ollama tool call from:
  - `POST http://192.168.1.12:11434/api/chat`
- the response included a structured `tool_calls` entry with:
  - function `get_temperature`
  - arguments `{ "city": "New York" }`

That proves two important things:

- the Mac-hosted Ollama path can support tool calls
- the current failure is not "all Mac inference is bad for tools"

## Exporter Change

`scripts/export-openclaw-config.sh` now supports provider-aware export overrides instead of forcing every external backend into `openai-completions`.

As of 2026-03-27, the repo default is now also native Ollama:

- committed provider source:
  - `services/openclaw-config/providers/local-ollama-native.yaml`
- committed default agent provider:
  - `local-ollama-native`
- default exported model ref:
  - `glasslab-ollama/qwen3:14b`

The old in-cluster `vllm` path remains in the repo only as an explicit legacy override.

New environment overrides:

- `GLASSLAB_OPENCLAW_PROVIDER_BASE_URL`
- `GLASSLAB_OPENCLAW_PROVIDER_API`
- `GLASSLAB_OPENCLAW_PROVIDER_ID`
- `GLASSLAB_OPENCLAW_PROVIDER_API_KEY_ENV`

Example native Ollama export:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://192.168.1.12:11434" \
GLASSLAB_OPENCLAW_PROVIDER_API="ollama" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="qwen3:14b" \
GLASSLAB_OPENCLAW_MODEL_ALIAS="glasslab-mac-ollama-qwen3" \
./scripts/export-openclaw-config.sh
```

This produces runtime config like:

- provider API: `ollama`
- provider base URL: `http://192.168.1.12:11434`
- model ref: `glasslab-ollama/qwen3:14b`

## Recommended Role Split Now

Use the Mac hosts as separate roles until a single model/runtime proves it can do both jobs well:

- `.23`: stronger plain inference, interpretation, summarization
- `.12`: first native-Ollama tool-capable candidate for OpenClaw experiments

Do not assume that a larger reasoning model is automatically the best OpenClaw tool model.

## Practical Next Step

The next clean experiment is:

1. export OpenClaw with native Ollama provider settings
2. target a model that already demonstrates native tool calls
3. rerun `./scripts/check-openclaw-tool-calling.sh` unchanged

If that works, the Mac path can become both:

- the main inference path
- the operator tool path

If it fails, keep the split:

- Mac for chat and bounded backend stages
- separate runtime/model lane for operator tool calling
