# Deploy Glasslab v2

1. Log into the provisioner host and move to the canonical repo.

```bash
ssh glasslab@192.168.1.44
cd /home/glasslab/cluster-config
```

2. Review the example secret manifests before applying anything.

```bash
sed -n '1,200p' kubeadm/glasslab-v2/postgres/10-secret.example.yaml
sed -n '1,200p' kubeadm/glasslab-v2/minio/10-secret.example.yaml
```

3. Create real secrets from those examples or apply locally edited copies that are not committed to Git.

4. Apply the initial v2 manifest tree in order.

```bash
./scripts/deploy-glasslab-v2.sh
```

5. Verify rollout state and the workflow-api health endpoint.

```bash
./scripts/smoke-test-v2.sh
```

6. If the smoke test fails, inspect the namespace directly.

```bash
kubectl -n glasslab-v2 get pods -o wide
kubectl -n glasslab-v2 describe deploy/glasslab-workflow-api
kubectl -n glasslab-v2 describe statefulset/glasslab-postgres
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --tail=200
```

7. Do not expose v2 publicly yet. Keep access internal until OpenClaw posture, auth, and policy manifests are in place.
