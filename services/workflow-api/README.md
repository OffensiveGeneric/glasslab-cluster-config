# Workflow API

`workflow-api` is the v2 orchestration backend. It accepts structured requests, validates them against the approved workflow registry, creates canonical run manifests, stores run state, and hands execution to a bounded job submission interface.


The first live execution path now targets Kubernetes Jobs in `glasslab-v2` for accepted `generic-tabular-benchmark` runs.

Planned bounded stage-agent integration starts with the interpretation stage. The
first config surfaces now reserved are:

- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_TIMEOUT_SECONDS`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_TIMEOUT_SECONDS`

Recent paper-intake endpoints:

- `POST /research-sessions`
- `GET /research-sessions`
- `GET /research-sessions/latest`
- `GET /research-sessions/latest/context`
- `POST /research-sessions/from-latest-research-problem`
- `POST /research-sessions/latest/research-problems/from-session-goal`
- `POST /research-sessions/latest/paper-intake-queues/from-latest-problem`
- `POST /research-sessions/latest/paper-intake-queues/stage-next-intake`
- `POST /paper-intake-queues/from-research-problem`
- `GET /paper-intake-queues`
- `GET /paper-intake-queues/latest`
- `GET /paper-intake-queues/{queue_id}`
- `POST /paper-intake-queues/{queue_id}/stage-next-intake`
- `GET /source-documents`
- `GET /source-documents/latest`
- `GET /source-documents/{document_id}`
- `GET /interpretations/latest`
- `GET /replicability-assessments/latest`
- `GET /workflow-families/{workflow_id}/execution-preflight`

These let `workflow-api` persist a bounded queue of harvested paper candidates
before interpretation/assessment/design work begins. The queue is intended to
run in the background while later paper-understanding work is still being
refined.

The newer session layer makes that state conversationally usable:

- a `ResearchSessionRecord` is now the stateful literature workspace
- sessions track the latest problem, queue, document, intake, interpretation,
  assessment, design, and run
- workflow families stay execution-oriented
- sessions are the stateful "how we think" layer for back-and-forth literature work

When a queued paper is staged, `workflow-api` now fetches the paper URL and
creates a `SourceDocumentRecord`. Storage is explicit:

- filesystem mode: writes under `GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_STORAGE_DIR`
- MinIO mode: writes to `GLASSLAB_WORKFLOW_API_SOURCE_DOCUMENT_BUCKET`

Interpretation now carries forward:

- `literature_state_summary`
- `research_gaps`
- `bounded_experiment_ideas`

and those outputs now inform later assessment and design stages instead of
stopping at the interpretation boundary.

Execution is also more explicit now:

- `workflow-api` exposes an execution-preflight result per workflow family
- run acceptance now checks that preflight before submission
- Kubernetes job submission now applies the registry-declared resource requests,
  limits, and node selector to the actual runner pod spec
