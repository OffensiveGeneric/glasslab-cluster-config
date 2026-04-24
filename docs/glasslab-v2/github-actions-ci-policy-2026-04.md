# GitHub Actions CI Policy 2026-04

This note defines the intended role of GitHub Actions in `glasslab-cluster-config`.

## Design Rule

GitHub-hosted Actions should validate repository state that is safe and meaningful
to run outside the lab.

They should not pretend to be the live Glasslab deployment system.

## What Default CI Should Do

The default GitHub Actions surface should stay small:

- parse YAML and JSON safely
- compile Python sources
- run unit tests that are known to pass on generic hosted runners
- validate deterministic backend/router/gateway behavior that does not require
  cluster access, GPUs, Thunderbolt, exo, or `.44`

## What Default CI Should Not Do

Do not run these on every push to `main`:

- cluster deployment
- manifest rewrites followed by `git push`
- GHCR image publication as a required path
- GPU jobs
- exo / RDMA validation
- `.44`-specific rollout steps
- broad meta-workflows that only validate other workflows

These create noise, false failures, and unsafe self-mutating automation.

## Manual-Only Work

The following classes of work should be manual-only via `workflow_dispatch`, or
kept outside GitHub Actions entirely:

- Docker image builds intended for publication
- release creation
- cluster-facing rollout logic
- any job that depends on repository or organization package permissions that are
  not already proven in GitHub

## Live Rollout Boundary

The canonical live rollout path remains the repo-owned operational flow from
`.44`.

GitHub Actions may support packaging or preflight validation, but they are not
the source of truth for cluster state.

## Current Hosted-Runner-Safe Test Surface

The current useful GitHub-hosted test surface is:

- `workflow-api` narrow unit tests:
  - `test_persistence.py`
  - `test_run_artifacts.py`
  - `test_validation.py`
- `research-ingress` API tests
- `research-command-router` API tests
- `whatsapp-gateway` API tests
- `evaluator` unit tests
- `reporter` unit tests

If a future workflow expands beyond that, it should prove two things first:

1. it passes on a generic hosted runner
2. it provides signal that is worth the email and branch protection cost
