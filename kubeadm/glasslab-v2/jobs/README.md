# Jobs

Glasslab v2 now uses Kubernetes Jobs as the bounded execution path for accepted workflow-api runs.

Current first-live assumptions:

- `workflow-api` creates Jobs in the `glasslab-v2` namespace
- the first wired workflow family is `generic-tabular-benchmark`
- datasets mount from the shared RWX PVC `glasslab-shared-datasets`
- artifacts mount from the shared RWX PVC `glasslab-shared-artifacts`
- the runner image is pulled through the `glasslab-ghcr-pull` secret

The current path is intentionally narrow. More workflow families should be added only after their runner contracts and storage assumptions are explicit.
