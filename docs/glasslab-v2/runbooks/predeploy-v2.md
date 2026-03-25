# Pre-Deploy Checklist

Complete these items before the first live Glasslab v2 deployment.

## Required local substitutions

- create `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml` with a real `POSTGRES_PASSWORD`
- create `kubeadm/glasslab-v2/secrets/20-minio.local.yaml` with a real `MINIO_ROOT_PASSWORD`
- keep those local files off Git

## Required image preparation

- `workflow-api` uses `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.8`
- bounded agents use:
  - `ghcr.io/offensivegeneric/glasslab-intake-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-interpretation-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-assessment-agent:0.1.0`
  - `ghcr.io/offensivegeneric/glasslab-design-agent:0.1.0`
- push the image to private GHCR before deployment
- create or refresh the `glasslab-ghcr-pull` secret in the `glasslab-v2` namespace before deployment
- the old `build-import-workflow-api-image.sh` helper is emergency fallback only

## Expected first-live compromises

- Postgres uses a retained static local PV/PVC on `node01`, so it survives pod replacement but not loss of that node
- MinIO uses a retained static local PV/PVC on `node01`, so object storage survives pod replacement but not loss of that node
- OpenClaw writable state uses a retained static local PV/PVC on `node01`, but the runtime bundle still unpacks into pod-local `emptyDir`
- OpenClaw is intentionally excluded from the default deploy path
- no public ingress should be created

## Core-only first deployment command set

```bash
./scripts/seed-registry.sh
GHCR_TOKEN="$(gh auth token)" ./scripts/push-workflow-api-image.sh
GHCR_TOKEN="$(gh auth token)" ./scripts/push-bounded-agent-images.sh
GHCR_TOKEN="$(gh auth token)" ./scripts/create-ghcr-pull-secret.sh
./scripts/deploy-glasslab-v2.sh
./scripts/smoke-test-v2.sh
```
