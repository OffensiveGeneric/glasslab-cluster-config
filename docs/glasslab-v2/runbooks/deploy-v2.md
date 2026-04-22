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

3. Create local non-committed core secret manifests under `kubeadm/glasslab-v2/secrets/`.

Recommended files:
- `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml`
- `kubeadm/glasslab-v2/secrets/20-minio.local.yaml`

Back them up separately. Git and `scripts/snapshot-provisioner-config.sh` do not capture these files.

4. Validate the workflow registry definitions.

```bash
./scripts/seed-registry.sh
```

5. Build and push the `workflow-api` image and bounded-agent images to private GHCR, then create or refresh the in-cluster pull secret.

```bash
GHCR_TOKEN="$(gh auth token)" ./scripts/push-workflow-api-image.sh
GHCR_TOKEN="$(gh auth token)" ./scripts/push-bounded-agent-images.sh
GHCR_TOKEN="$(gh auth token)" ./scripts/create-ghcr-pull-secret.sh
```

Current assumptions:
- the `glasslab-v2` namespace contains a `glasslab-ghcr-pull` Docker registry secret
- the shared PVCs `glasslab-shared-datasets` and `glasslab-shared-artifacts` exist and are `Bound`
- the `workflow-api` Deployment pulls `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.8`
- the bounded-agent Deployments pull:
  - `ghcr.io/offensivegeneric/glasslab-intake-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-interpretation-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-assessment-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-design-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-schedule-worker:0.1.0`
- the old import helper remains available as a fallback if GHCR is unavailable

Prereq check:

```bash
./scripts/check-v2-run-prereqs.sh
```

6. Apply the initial v2 core manifest tree.

```bash
./scripts/deploy-glasslab-v2.sh
```

The deploy script applies local files in `kubeadm/glasslab-v2/secrets/` and skips any `*.example.yaml` manifests.

It also applies the first explicit scheduling lanes:

- `glasslab-user-high`
- `glasslab-autonomous-low`

Current storage caveat:
- Postgres and MinIO are still non-durable until the storage plan under `docs/glasslab-v2/storage-and-state.md` is implemented

7. Verify rollout state and the workflow-api health endpoints.

```bash
./scripts/smoke-test-v2.sh
./scripts/smoke-test-v2.sh --include-bounded-agents
./scripts/check-live-provenance.sh
```

The provenance check should make drift obvious:

- `workflow-api` should report the expected `build_source_revision` and `build_source_label`
- if provenance is missing, the rollout is incomplete even if pods are `Running`

Bounded-agent rollout check:

```bash
kubectl -n glasslab-v2 rollout status deployment/glasslab-intake-agent --timeout=120s
kubectl -n glasslab-v2 rollout status deployment/glasslab-interpretation-agent --timeout=120s
kubectl -n glasslab-v2 rollout status deployment/glasslab-assessment-agent --timeout=120s
kubectl -n glasslab-v2 rollout status deployment/glasslab-design-agent --timeout=120s
kubectl -n glasslab-v2 rollout status deployment/glasslab-schedule-worker --timeout=120s
```

8. If the smoke test fails, inspect the namespace directly.

```bash
kubectl -n glasslab-v2 get pods -o wide
kubectl -n glasslab-v2 describe deploy/glasslab-workflow-api
kubectl -n glasslab-v2 describe statefulset/glasslab-postgres
kubectl -n glasslab-v2 logs deploy/glasslab-workflow-api --tail=200
```

9. If the rollout fails with image pull errors, verify the private registry secret before falling back to a manual import.

```bash
kubectl -n glasslab-v2 get secret glasslab-ghcr-pull
kubectl -n glasslab-v2 describe pod -l app.kubernetes.io/name=glasslab-workflow-api
```

10. Do not expose v2 publicly yet. Keep access internal until the deterministic WhatsApp/control path and backend policies are fully validated.

11. Keep all bounded-agent feature flags disabled in `workflow-api` until each service has been deployed and tested one stage at a time.

Reference:

- `runbooks/deploy-bounded-agents.md`
