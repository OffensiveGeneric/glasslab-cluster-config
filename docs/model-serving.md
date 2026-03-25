# Model Serving Notes

## vLLM / Qwen

This stack started with a single in-cluster vLLM Deployment exposing an OpenAI-compatible `/v1` API inside the `glasslab-agents` namespace.

That is still the safe repo default, but Glasslab can also treat a separate inference host such as a Mac Studio as the primary model-serving tier if it exposes a stable OpenAI-compatible `/v1` endpoint reachable from the cluster.

Configured environment keys:

- `MODEL_NAME`
- `MAX_MODEL_LEN`
- `VLLM_API_KEY`
- `HUGGING_FACE_HUB_TOKEN`

Current manifest assumptions:

- service name: `vllm`
- service port: `8000`
- runtime class: `nvidia`
- node selector: `glasslab.io/gpu-candidate=true`
- GPU resource key: `nvidia.com/gpu`
- cache PVC: `vllm-model-cache`

Validation path after deployment:

```bash
/home/glasslab/cluster-config/scripts/port-forward-vllm.sh
/home/glasslab/cluster-config/scripts/test-vllm.sh
```

The agent API talks to:

- `http://vllm.glasslab-agents.svc.cluster.local:8000/v1/models`
- `http://vllm.glasslab-agents.svc.cluster.local:8000/v1/chat/completions`

## External Primary Inference

If the Mac Studio becomes the main inference box, the cleanest path is:

- keep the Mac outside the Kubernetes worker set
- expose a stable internal or Tailscale-reachable OpenAI-compatible `/v1` endpoint
- point OpenClaw at that endpoint during runtime export
- update any legacy v1 `agent-api` config that still depends on the old in-cluster `vllm` service

Example OpenClaw export override:

```bash
GLASSLAB_OPENCLAW_PROVIDER_BASE_URL="https://mac-studio.example.internal/v1" \
GLASSLAB_OPENCLAW_DEFAULT_MODEL="your-primary-model-id" \
./scripts/export-openclaw-config.sh
```

Example smoke test against a non-default endpoint and model:

```bash
VLLM_BASE_URL="https://mac-studio.example.internal/v1" \
VLLM_MODEL_NAME="your-primary-model-id" \
./scripts/test-vllm.sh
```

## Planner Behavior

The planner prompt is intentionally narrow.

Rules:

- only the Titanic baseline is supported
- output must be JSON only
- no shell, Python, or YAML is accepted
- unknown models or resource profiles are rejected by the validator even if the model invents them

A deterministic fallback parser exists for common Titanic requests so the API remains testable when model output is missing or malformed.

## Optional MLflow

`kubeadm/agent-stack/30-mlflow-optional.yaml` is a minimal optional deployment.

What it does now:

- starts one `mlflow server`
- uses a single PVC-backed sqlite backend store
- exposes `mlflow` as a ClusterIP service on port `5000`

What it does not try to solve yet:

- production auth
- external object storage
- HA database backing
- ingress

The runner only logs to MLflow when these settings are enabled:

- `GLASSLAB_AGENT_MLFLOW_ENABLED=true`
- `GLASSLAB_AGENT_MLFLOW_TRACKING_URI=http://mlflow.glasslab-agents.svc.cluster.local:5000`
