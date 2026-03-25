# Schedule Worker

ClusterIP deployment manifests for the bounded `schedule-worker` service live here.

Current intended role:

- call the bounded `workflow-api` due-digest execution path
- remain internal-only in `glasslab-v2`
- stay limited to digest execution first
- avoid arbitrary job scheduling or free-form agent control
