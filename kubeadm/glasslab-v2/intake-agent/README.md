# Intake Agent

ClusterIP deployment manifests for the bounded `intake-agent` service live here.

Current intended role:

- normalize raw intake requests behind `workflow-api`
- remain internal-only in `glasslab-v2`
- stay feature-flagged off in `workflow-api` until explicitly enabled
