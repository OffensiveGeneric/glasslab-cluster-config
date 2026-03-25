# Workflow API

`workflow-api` is the v2 orchestration backend. It accepts structured requests, validates them against the approved workflow registry, creates canonical run manifests, stores run state, and hands execution to a bounded job submission interface.


The first live execution path now targets Kubernetes Jobs in `glasslab-v2` for accepted `generic-tabular-benchmark` runs.

Planned bounded stage-agent integration starts with the interpretation stage. The
first config surface is already reserved:

- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_TIMEOUT_SECONDS`
