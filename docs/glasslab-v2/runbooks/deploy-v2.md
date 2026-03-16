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
sed -n '1,200p' kubeadm/glasslab-v2/openclaw/10-secret.example.yaml
```

3. Create local non-committed core secret manifests under `kubeadm/glasslab-v2/secrets/`.

Recommended files:
- `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml`
- `kubeadm/glasslab-v2/secrets/20-minio.local.yaml`

Back them up separately. Git and `scripts/snapshot-provisioner-config.sh` do not capture these files.

4. Validate the workflow registry definitions.

```bash
./scripts/seed-registry.sh
```

5. Build the `workflow-api` image on the provisioner and import it into `node03` containerd.

```bash
./scripts/build-import-workflow-api-image.sh
```

Current limitation:
- `workflow-api` is pinned to `node03`
- the image import must be repeated after each rebuild
- this is a temporary manual distribution path, not the steady-state release flow

6. Apply the initial v2 core manifest tree.

```bash
./scripts/deploy-glasslab-v2.sh
```

The deploy script applies local files in `kubeadm/glasslab-v2/secrets/` and skips any `*.example.yaml` manifests.

Current storage caveat:
- Postgres and MinIO are still non-durable until the storage plan under `docs/glasslab-v2/storage-and-state.md` is implemented

7. Verify rollout state and the workflow-api health endpoints.

```bash
./scripts/smoke-test-v2.sh
```

8. OpenClaw is intentionally excluded from the default deploy path. Do not deploy it until the runtime bundle, local secret manifest, and in-cluster service references are confirmed.

OpenClaw predeploy checklist:
- create `kubeadm/glasslab-v2/secrets/30-openclaw.local.yaml`
- confirm `kubectl -n glasslab-v2 get svc glasslab-workflow-api`
- confirm `kubectl -n glasslab-agents get svc vllm`
- inspect the generated runtime tree with `./scripts/export-openclaw-config.sh --output-dir /tmp/openclaw-runtime --no-apply`
- verify `/tmp/openclaw-runtime/openclaw.json` contains the expected `workflow-api` and `vLLM` cluster URLs
- keep `replicas: 0` until the predeploy checklist is complete

```bash
./scripts/deploy-glasslab-v2.sh --include-openclaw
./scripts/smoke-test-v2.sh --include-openclaw
```

9. If the smoke test fails, inspect the namespace directly.

```bash
kubectl -n glasslab-v2 get pods -o wide
kubectl -n glasslab-v2 describe deploy/glasslab-workflow-api
kubectl -n glasslab-v2 describe statefulset/glasslab-postgres
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --tail=200
```

10. Do not expose v2 publicly yet. Keep access internal until OpenClaw posture, auth, and policy manifests are in place.
