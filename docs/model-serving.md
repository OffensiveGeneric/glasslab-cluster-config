# Model Serving Notes

## vLLM / Qwen

This stack assumes a single vLLM Deployment exposing an OpenAI-compatible `/v1` API inside the `glasslab-agents` namespace.

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
