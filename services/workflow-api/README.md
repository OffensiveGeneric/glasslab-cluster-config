# Workflow API

`workflow-api` is the v2 orchestration backend. It accepts structured requests, validates them against the approved workflow registry, creates canonical run manifests, stores run state, and hands execution to a bounded job submission interface.


The first live execution path now targets Kubernetes Jobs in `glasslab-v2` for accepted `generic-tabular-benchmark` runs.
