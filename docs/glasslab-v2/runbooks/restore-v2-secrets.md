# Restore Glasslab v2 Secrets

1. Log into the provisioner and move to the canonical repo.

```bash
ssh glasslab@192.168.1.44
cd /home/glasslab/cluster-config
```

2. Restore the encrypted backup contents into the local secret paths.

Required files:

- `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml`
- `kubeadm/glasslab-v2/secrets/20-minio.local.yaml`
- `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml` if OpenClaw is in use

Related v1 file if the copied vLLM API key must also be restored:

- `kubeadm/agent-stack/12-agent-secrets.yaml`

3. Lock down file permissions.

```bash
chmod 600 kubeadm/glasslab-v2/secrets/*.local.yaml
chmod 600 kubeadm/agent-stack/12-agent-secrets.yaml 2>/dev/null || true
```

4. Review the manifests before applying them.

```bash
sed -n '1,200p' kubeadm/glasslab-v2/secrets/10-postgres.local.yaml
sed -n '1,200p' kubeadm/glasslab-v2/secrets/20-minio.local.yaml
sed -n '1,200p' kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml 2>/dev/null || true
```

5. Apply the restored secrets.

```bash
kubectl apply -f kubeadm/glasslab-v2/secrets/
```

6. If the v1 secret file was restored or rotated too, apply it separately.

```bash
kubectl apply -f kubeadm/agent-stack/12-agent-secrets.yaml
```

7. Restart the workloads that read those secrets from environment variables.

```bash
kubectl -n glasslab-v2 rollout restart statefulset/glasslab-postgres
kubectl -n glasslab-v2 rollout restart deployment/glasslab-minio
kubectl -n glasslab-v2 rollout restart deployment/glasslab-openclaw 2>/dev/null || true
kubectl -n glasslab-agents rollout restart deployment/vllm 2>/dev/null || true
kubectl -n glasslab-agents rollout restart deployment/glasslab-agent-api 2>/dev/null || true
```

8. Wait for the affected workloads to settle.

```bash
kubectl -n glasslab-v2 rollout status statefulset/glasslab-postgres --timeout=300s
kubectl -n glasslab-v2 rollout status deployment/glasslab-minio --timeout=300s
kubectl -n glasslab-v2 rollout status deployment/glasslab-openclaw --timeout=300s 2>/dev/null || true
kubectl -n glasslab-agents rollout status deployment/vllm --timeout=1200s 2>/dev/null || true
```

9. Re-run the core validation path.

```bash
./scripts/smoke-test-v2.sh
kubectl -n glasslab-v2 get secret glasslab-v2-postgres glasslab-v2-minio glasslab-openclaw 2>/dev/null || true
```

10. If the original secret values are not available, generate new values, update the local manifests, apply them, and treat the restore as a rotation event.
