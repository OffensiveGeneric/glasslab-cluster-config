# Contributing To Glasslab

Glasslab is being simplified around one primary learning-task path:

```text
OpenCode -> exo -> repo-owned scripts -> workflow-api -> Kubernetes Job
```

Contributions should either strengthen that path or clearly label themselves as
secondary, compatibility-only, or historical.

## Start Here

Read these first:

- `README.md`
- `docs/glasslab-v2/current/README.md`
- `docs/glasslab-v2/system-map-2026-07.md`
- `docs/glasslab-v2/ci-policy-2026-07.md`
- `docs/glasslab-v2/learning-task-flow.md`

## Before Pushing

Run the default local check:

```bash
./scripts/check-before-push.sh
```

Narrower modes are available when you are making a small scoped change:

```bash
./scripts/check-before-push.sh --docs
./scripts/check-before-push.sh --configs
./scripts/check-before-push.sh --python-core
```

The default check mirrors the default CI signal:

- current YAML/JSON parsing
- Markdown link resolution
- shell syntax for primary operator scripts
- Python syntax for services
- workflow-api core tests

## CI Lanes

Default GitHub checks are intentionally small and path-aware.

| Lane | Purpose |
| --- | --- |
| `CI Python` | service Python syntax and workflow-api core tests |
| `CI Configs` | YAML/JSON syntax for current configs |
| `CI Docs` | local Markdown link checks |
| `CI Scripts` | shell syntax for repo scripts |
| `CodeQL` | GitHub code scanning |

Manual compatibility tests remain available through `workflow_dispatch` on
`CI Python`. Use them when touching adapters, reporter/evaluator, or heavyweight
runner code.

## Ownership Boundaries

Use `cluster-config` for:

- physical lab and Kubernetes infrastructure
- workflow-api and workflow-registry
- generic run submission, records, comparisons, and deployment scripts
- current system docs and runbooks

Use workload repos such as `glasslab-metric-search` for:

- dataset protocols
- model/loss/miner/trainer code
- emitted metrics schema
- workload image build context

Do not add Kubernetes topology, WhatsApp routing, or global run records to a
scientific workload repo.

## Live State

The laptop checkout is not authoritative for live state.

- `.44` is the canonical provisioner and live operations checkout.
- GitHub is committed repo state.
- Docs are documented state.
- Only `.44` can confirm actual live cluster state.

If a change affects a live service, roll it from `.44` using the service rollout
helper and run the smoke test before calling it live.

For workflow-api:

```bash
ssh glasslab-44
cd /home/glasslab/cluster-config
./scripts/rollout-workflow-api-live.sh
```

## Pull Request Expectations

A useful PR should say:

- what area it changes
- whether it touches the primary path or a secondary/compatibility path
- what local checks were run
- whether live rollout is required
- what docs changed if behavior changed

When in doubt, prefer a small PR that improves the current path over a broad PR
that adds another competing path.
