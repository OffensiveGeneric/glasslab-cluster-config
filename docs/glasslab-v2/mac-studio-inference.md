# Mac Studio Inference Path

This note records the current preferred use of the available Mac Studio systems for Glasslab.

## Decision

Treat the Mac Studio as an external inference host, not as a Kubernetes worker.

Why:

- the current cluster and kubeadm path are Linux-centric
- OpenClaw only needs an OpenAI-compatible inference endpoint, not a macOS node join
- keeping the Mac outside the cluster avoids introducing arm64 worker scheduling and OS-mix complexity into the current lab
- this is the smallest operational change that still allows a much larger local model than the current in-cluster `vLLM` path

## Observed Mac hosts

Validated on `2026-03-24`:

### `192.168.1.23`

- hostname: `CS60140N7311`
- hardware: `Mac Studio`
- chip: `Apple M4 Max`
- memory: `64 GB`
- inference service: `Ollama 0.18.2`
- listener: `*:11434`
- current role: primary external inference host
- current state:
  - `ollama list` shows `deepseek-r1:32b`
  - `/api/tags` returns `deepseek-r1:32b`
  - `/v1/models` returns `deepseek-r1:32b`
  - direct chat smoke test from `.44` succeeded
  - OpenClaw was first re-exported against `http://192.168.1.23:11434/v1`
  - the live `glasslab-openclaw` Deployment is now running against that backend for plain inference
  - native Ollama tool probing against `deepseek-r1:32b` returns:
    - `registry.ollama.ai/library/deepseek-r1:32b does not support tools`
  - `qwen3:30b` pull has been started there as the next tool-capable candidate to test in native Ollama mode

This host is now the active primary external inference path for OpenClaw chat inference, but not yet the validated long-term tool backend.

### `192.168.1.12`

- hostname: `CS60123N7311`
- hardware: `Mac Studio`
- chip: `Apple M4 Max`
- memory: `48 GB`
- current role: secondary inference and ranker host
- current state:
  - `Ollama 0.18.2` is installed and listening on `*:11434`
  - `ollama list` and `/v1/models` return `qwen3:14b`
  - native Ollama `POST /api/chat` returns structured `tool_calls` for `qwen3:14b`
  - a bounded ranker wrapper is running on `http://192.168.1.12:8181`
  - `GET /healthz` succeeds
  - `POST /rank/workflow-family` succeeds against the repo request shape

This host is now the live secondary Apple-silicon service box for ranker work and the first proven native-Ollama tool candidate.

## Recommended role

Use the Mac Studio fleet for:

- primary OpenClaw inference
- bounded ranker or reranker serving
- model experiments that do not need to run inside Kubernetes
- possible future ranking or report-generation assistance if a separate local service is useful

Do not use the Mac Studio first as:

- a kubeadm worker node
- the place to move cluster stateful services
- a dependency for core Kubernetes control plane behavior

## Current live endpoints

- primary inference:
  - `http://192.168.1.23:11434/v1`
  - model: `deepseek-r1:32b`
- secondary inference:
  - `http://192.168.1.12:11434/v1`
  - model: `qwen3:14b`
- native Ollama tool candidate:
  - `http://192.168.1.12:11434`
  - model: `qwen3:14b`
- ranker:
  - `http://192.168.1.12:8181`
  - endpoints:
    - `GET /healthz`
    - `POST /rank/workflow-family`

## OpenClaw switch path

Keep the committed provider YAML on the safe in-cluster default.

The first working chat-only cutover used:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://192.168.1.23:11434/v1" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="deepseek-r1:32b" \
GLASSLAB_OPENCLAW_MODEL_ALIAS="glasslab-mac-studio-primary" \
./scripts/export-openclaw-config.sh
```

This override path has now been used successfully on `.44`.

But the current better path for Ollama-backed tool experiments is native provider mode:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="http://192.168.1.12:11434" \
GLASSLAB_OPENCLAW_PROVIDER_API="ollama" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="qwen3:14b" \
GLASSLAB_OPENCLAW_MODEL_ALIAS="glasslab-mac-ollama-qwen3" \
./scripts/export-openclaw-config.sh
```

The exporter now supports that native-Ollama path explicitly.

The remaining caveats are:

- compatibility drift between newer generated plugin configs and the currently pinned OpenClaw image
- model-level tool support still needs to be validated per model, not assumed from Ollama alone

## Validation sequence

1. Confirm the model is present on the host:
   `/Applications/Ollama.app/Contents/Resources/ollama list`
2. Confirm the remote API reports the model:
   `curl http://192.168.1.23:11434/api/tags`
3. For native Ollama tool candidates, run a direct native tool smoke test against `/api/chat`.
4. For OpenAI-compatible chat-only checks, confirm:
   `curl http://192.168.1.23:11434/v1/models`
5. Run a direct generation smoke test against the endpoint.
6. For the ranker host, validate:
   `curl http://192.168.1.12:8181/healthz`
7. Re-run the bounded ranking smoke request against `POST /rank/workflow-family`.
8. Re-export OpenClaw runtime with the Mac overrides.
9. Re-run the OpenClaw tool-calling harness unchanged against the new backend.

## Why this is enough for now

The immediate goal is better primary inference, not an arm64 cluster expansion project.

If the Mac Studio path proves stable, Glasslab can later decide whether separate Apple-silicon hosts should also take on bounded sidecar services or Linux arm64 VM experiments.
