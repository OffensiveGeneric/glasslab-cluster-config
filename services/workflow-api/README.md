# Workflow API

`workflow-api` is the v2 orchestration backend. It accepts structured requests, validates them against the approved workflow registry, creates canonical run manifests, stores run state, and hands execution to a bounded job submission interface.

Current architectural reality:

- sessions are becoming the primary product object
- skills/stages mutate session-owned state
- workflow families are increasingly execution templates, not the whole ontology
- mutating `latest` routes are still present for operator convenience, but should not be treated as the durable primary contract for automation

Current durability warning:

- the store backend is now explicit:
  - `GLASSLAB_WORKFLOW_API_STORE_BACKEND=memory`
  - `GLASSLAB_WORKFLOW_API_STORE_BACKEND=json`
- in-memory mode is still valid for tests and short-lived local iteration
- `GLASSLAB_WORKFLOW_API_ALLOW_INMEMORY_STORE=false` can now fail closed instead of silently booting on ephemeral state
- the first durable backend is JSON-file based via `GLASSLAB_WORKFLOW_API_STORE_JSON_PATH`
- session and stage metadata are still not in Postgres yet, so this is a bounded durability step rather than the final persistence architecture
- artifact files and source-document blobs may be durable, but the coordinating metadata currently is not

Current execution prerequisites:

- dataset PVC: `glasslab-shared-datasets`
- artifacts PVC: `glasslab-shared-artifacts`
- image pull secret: `glasslab-ghcr-pull`
- service account RBAC able to read:
  - PVCs and secrets in `glasslab-v2`
  - cluster `nodes`
  - cluster `pods`

The repo now includes a direct prereq checker:

- `/home/gr66ss/cluster-config/scripts/check-v2-run-prereqs.sh`

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

Session-first skill endpoints:

- `POST /research-sessions/{session_id}/skills/research-problem`
- `POST /research-sessions/{session_id}/skills/literature-harvest`
- `POST /research-sessions/{session_id}/skills/paper-intake`
- `POST /research-sessions/latest/skills/research-problem`
- `POST /research-sessions/latest/skills/literature-harvest`
- `POST /research-sessions/latest/skills/paper-intake`

These are thin bounded aliases over the existing session-state path. The intent is:

- sessions hold the research state
- skills mutate that state in bounded ways
- workflow families stay a later execution concern

Operation-record endpoints:

- `GET /operations`
- `GET /operations/latest`
- `GET /operations/{operation_id}`

The first covered operation types are:

- `literature-harvest`
- `source-document-fetch`
- `paper-intake`

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
- workflow registry entries now declare:
  - `execution_status`
  - `submission_backend`
  - `execution_blockers`
- this lets preflight report "declared but not executable" instead of over-promising from the registry alone
