## Schedule Worker

`schedule-worker` is a bounded backend worker for unattended Glasslab v2 operations.

Current scope:

- `GET /healthz`
- `POST /run-once`
- executes only due digest schedules through `workflow-api`
- does not infer workflows or submit arbitrary jobs

The intended deployment shape is:

- namespace: `glasslab-v2`
- deployment: `glasslab-schedule-worker`
- service: `glasslab-schedule-worker`
- service type: `ClusterIP`

Current environment:

- `GLASSLAB_SCHEDULE_WORKER_WORKFLOW_API_URL`
- `GLASSLAB_SCHEDULE_WORKER_TIMEOUT_SECONDS`

The worker is deliberately narrow. It calls the bounded `workflow-api` digest execution path and returns the execution records it received.
