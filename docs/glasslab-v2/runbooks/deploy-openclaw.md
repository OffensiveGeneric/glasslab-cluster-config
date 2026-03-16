# Deploy OpenClaw

1. Log into the provisioner host and move to the canonical repo.

```bash
ssh glasslab@192.168.1.44
cd /home/glasslab/cluster-config
```

2. Verify the backend services OpenClaw depends on already exist.

```bash
kubectl -n glasslab-v2 get svc glasslab-workflow-api
kubectl -n glasslab-agents get svc vllm
```

For the backend-facing operator validation path, verify the live `vllm` deployment includes tool-call support:

```bash
kubectl -n glasslab-agents get deploy vllm -o yaml | grep -E 'enable-auto-tool-choice|tool-call-parser'
```

3. Review the example secret manifest.

```bash
sed -n '1,200p' kubeadm/glasslab-v2/openclaw/10-secret.example.yaml
```

4. Create the required local non-committed OpenClaw secret manifest.

Required file:
- `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`

Required keys:
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_VLLM_API_KEY`

Example creation flow:

```bash
VLLM_API_KEY="$(kubectl -n glasslab-agents get secret glasslab-agent-secrets -o jsonpath='{.data.VLLM_API_KEY}' | base64 -d)"
cat > kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: glasslab-openclaw
  namespace: glasslab-v2
type: Opaque
stringData:
  OPENCLAW_GATEWAY_TOKEN: $(openssl rand -hex 32)
  OPENCLAW_VLLM_API_KEY: ${VLLM_API_KEY}
EOF
chmod 600 kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml
```

5. Render the native runtime bundle locally and inspect it before applying it to the cluster.

```bash
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
find /tmp/openclaw-runtime -maxdepth 3 -type f | sort
python3 -m json.tool /tmp/openclaw-runtime/openclaw.json | sed -n '1,240p'
```

6. Verify the generated runtime contract before scaling anything.

Confirm:
- `openclaw.json` exists
- `workspaces/operator/IDENTITY.md` exists
- `workspaces/literature/IDENTITY.md` exists
- `workspaces/designer/IDENTITY.md` exists
- `workspaces/reporter/IDENTITY.md` exists
- `openclaw.json` points at `http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080`
- `openclaw.json` points at `http://vllm.glasslab-agents.svc.cluster.local:8000/v1`

7. Apply the exported runtime bundle and the OpenClaw manifests. Keep the Deployment at `replicas: 0`.

```bash
./scripts/export-openclaw-config.sh
kubectl apply -f kubeadm/glasslab-v2/openclaw/
kubectl -n glasslab-v2 get deploy glasslab-openclaw -o jsonpath='{.spec.replicas}{"\n"}'
```

Operator note:
- the repo manifest intentionally keeps `glasslab-openclaw` at `replicas: 0`
- a raw `kubectl apply -f kubeadm/glasslab-v2/openclaw/` should not silently turn on the gateway
- scaling to `1` is a separate deliberate validation or operating step
- if the live deployment is already at `1`, a future raw apply will scale it back to `0` unless you scale it up again on purpose

8. Verify the pre-scale state.

```bash
kubectl -n glasslab-v2 get configmap glasslab-openclaw-config
kubectl -n glasslab-v2 get secret glasslab-openclaw
kubectl -n glasslab-v2 describe deploy/glasslab-openclaw
```

9. When the runtime bundle and secrets look correct, scale from `0` to `1`.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=1
kubectl -n glasslab-v2 rollout status deploy/glasslab-openclaw --timeout=300s
kubectl -n glasslab-v2 get pods -l app.kubernetes.io/name=glasslab-openclaw -o wide
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200
```

10. Verify internal-only access and mounted runtime state.

```bash
kubectl -n glasslab-v2 port-forward svc/glasslab-openclaw 18789:18789
```

In another shell:

```bash
curl -I http://127.0.0.1:18789
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- ls -R /var/lib/openclaw/runtime | sed -n '1,200p'
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- sed -n '1,200p' /var/lib/openclaw/runtime/RUNTIME-CONTRACT.md
```

11. Validate the first backend-backed operator path from the deployed OpenClaw pod.

This repo exports the operator agent with a narrow runtime tool surface:
- repo-managed `workflow_api_get_families` plugin tool for internal backend reads
- no shell or filesystem mutation tools
- no unattended execution tools

Use the live pod to ask the operator for the approved workflow families.

```bash
kubectl -n glasslab-v2 exec deploy/glasslab-openclaw -- \
  openclaw agent --local --agent operator --json \
  --message 'List the approved Glasslab v2 workflow families and summarize each briefly.'
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --tail=50
```

Expected validation result:
- the operator returns a backend-backed summary of the available workflow families
- `workflow-api` logs show a live `GET /workflow-families` from the OpenClaw pod
- the request path is:
  - operator agent
  - `workflow_api_get_families`
  - `GET http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080/workflow-families`
  - plugin JSON result with `endpoint` and `workflow_families`
  - operator summary in `payloads[0].text`
- the response shape includes:
  - `payloads[].text` with the human-facing summary
  - `meta.systemPromptReport.tools.entries[]` containing `workflow_api_get_families`

Observed live validation on 2026-03-16:

```bash
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --since=2m | grep 'GET /workflow-families'
```

Client caveat:
- the separate helper pod may still show `Unknown agent id "operator"` with some CLI flows
- treat that as a client-side caveat unless the deployed OpenClaw pod itself cannot complete the validation command above

12. If startup fails, scale back to `0`, inspect the logs, and re-export the runtime bundle before trying again.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=0
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200 || true
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
```

13. Roll back by disabling the deployment and restoring the prior runtime bundle.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=0
kubectl -n glasslab-v2 delete configmap glasslab-openclaw-config
./scripts/export-openclaw-config.sh
kubectl -n glasslab-v2 rollout undo deploy/glasslab-openclaw || true
```
