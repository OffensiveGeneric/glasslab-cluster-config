# Live State Report: 2026-03-23

This note records what was validated from `.44` during the 2026-03-23 lab session.

It should be treated as the latest documented live-state checkpoint in the repo.

## Core Cluster

- all Kubernetes nodes were usable during the session
- shared NFS from `192.168.1.207:/volume1/backup` is live and mounted through static RWX PV/PVCs
- tracked shared reservation is now:
  - `glasslab-shared-datasets`: `2Ti`
  - `glasslab-shared-artifacts`: `3Ti`

## Durable Service State

The first durability phase is complete.

- `Postgres` persists on a retained local PV on `node01`
- `MinIO` persists on a retained local PV on `node01`
- OpenClaw writable state persists on a retained local PV on `node01`
- `NATS` JetStream data persists on a retained local PV on `node05`

This means the core v2 services now survive pod replacement.

This does not yet mean they survive node loss.

## Image Distribution

`workflow-api` is no longer tied to `.44` -> tarball import -> `node03`.

- private GHCR is now in active use for `workflow-api`
- the live deployment pulls via the `glasslab-ghcr-pull` secret
- the deployment was validated on a non-`node03` worker

Current validated image line during this session:

- `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.4`

## OpenClaw

OpenClaw remains the internal operator gateway.

- the live no-arg tool path is working
- OpenClaw runtime was refreshed and the new workflow-api-backed tools were validated
- OpenClaw still depends on `.44` for runtime export and deploy flow
- the argumented tool path is still limited by the missing reachable `tool_choice` control surface

## Intake -> Design -> Run Flow

The first backend-owned v2 workflow spine is now live.

`workflow-api` now supports:

- `POST /intakes`
- `GET /intakes/latest`
- `GET /intakes/{intake_id}`
- `POST /design-drafts/from-latest-intake`
- `GET /design-drafts/latest`
- `GET /design-drafts/{design_id}`
- `POST /runs/from-latest-design-draft`

The current no-arg OpenClaw path now covers:

- start paper intake
- get latest intake
- create design draft from latest intake
- get latest design draft
- create validation run from latest design
- get latest run status
- get latest run artifacts
- get latest run logs

## Real Execution Path

Accepted `generic-tabular-benchmark` runs now create real Kubernetes Jobs.

Live validated run during this session:

- run id: `b319c03c5a40472c981f924c9a0f2538`
- job name: `generic-tabular-benchmark-b319c03c`
- result: `succeeded`

The runner now writes the first usable v2 artifact contract into the shared artifacts PVC, including:

- `config.json`
- `run_manifest.json`
- `status.json`
- `report.md`
- `artifacts_index.json`
- `logs/runner.log`
- `metrics.json`
- `result_payload.json`
- `submission.csv`

`workflow-api` follow-up endpoints now read real artifact and log data from the shared artifacts PVC instead of relying only on placeholder in-memory metadata.

## Practical Takeaway

At the end of the 2026-03-23 session, Glasslab v2 is no longer just a set of mostly-separate validated components.

It now has a live, backend-owned, no-arg operator path that can:

- create intake
- derive a design draft
- create an accepted run
- submit a real Kubernetes Job
- expose real run status, artifacts, and logs

The next phase should focus on broadening that backbone rather than chasing broad argumented-tool orchestration.
