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

11. If startup fails, scale back to `0`, inspect the logs, and re-export the runtime bundle before trying again.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=0
kubectl -n glasslab-v2 logs deploy/glasslab-openclaw --tail=200 || true
./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply
```

12. Roll back by disabling the deployment and restoring the prior runtime bundle.

```bash
kubectl -n glasslab-v2 scale deploy/glasslab-openclaw --replicas=0
kubectl -n glasslab-v2 delete configmap glasslab-openclaw-config
./scripts/export-openclaw-config.sh
kubectl -n glasslab-v2 rollout undo deploy/glasslab-openclaw || true
```
