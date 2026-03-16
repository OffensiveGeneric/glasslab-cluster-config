# Pre-Deploy Checklist

Complete these items before the first live Glasslab v2 deployment.

## Required local substitutions

- create `kubeadm/glasslab-v2/secrets/10-postgres.local.yaml` with a real `POSTGRES_PASSWORD`
- create `kubeadm/glasslab-v2/secrets/20-minio.local.yaml` with a real `MINIO_ROOT_PASSWORD`
- keep those local files off Git

## Required image preparation

- `workflow-api` uses `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.0`
- that image is not assumed to be published
- build it on the provisioner and import it into `node03` before deployment
- `workflow-api` is pinned to `node03` for this first deployment path

## Expected first-live compromises

- Postgres uses `emptyDir`, so state is not durable yet
- MinIO uses `emptyDir`, so object storage is not durable yet
- OpenClaw is intentionally excluded from the default deploy path
- no public ingress should be created

## Core-only first deployment command set

```bash
./scripts/seed-registry.sh
./scripts/build-import-workflow-api-image.sh
./scripts/deploy-glasslab-v2.sh
./scripts/smoke-test-v2.sh
```
