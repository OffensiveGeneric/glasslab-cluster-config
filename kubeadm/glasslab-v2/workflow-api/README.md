# Workflow API

Deployment manifests for the v2 `workflow-api` service live here.

Current prerequisite boundary for execution preflight and run submission:

- shared datasets PVC: `glasslab-shared-datasets`
- shared artifacts PVC: `glasslab-shared-artifacts`
- image pull secret: `glasslab-ghcr-pull`
- service account: `glasslab-workflow-api`

The service account needs:

- namespace-scoped read access to PVCs and secrets in `glasslab-v2`
- cluster-scoped read access to:
  - `nodes`
  - `pods`

Those reads are required because execution preflight checks:

- whether the dataset and artifacts PVCs exist and are `Bound`
- whether the image pull secret exists
- whether any `Ready` nodes currently satisfy the requested resource profile
- current pod allocations when estimating node fit

If these prerequisites are missing, the operator path will surface infrastructure blockers before a run is accepted.
