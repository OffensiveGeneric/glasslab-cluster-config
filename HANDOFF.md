# Glasslab Current Handoff

Last updated: 2026-08-13

This is the compact current-state checkpoint for switching human or coding
agents. Read `AGENTS.md` first for stable rules, architecture, vocabulary,
access paths, and live inspection commands. Read `TODO.md` for the prioritized
work queue.

## Live Infrastructure Facts

The research orchestrator runs as a single pod on `node05`. Its state and
per-run workspaces are on `glasslab-shared-artifacts`, backed by NFS at:

```text
192.168.1.207:/volume1/backup/glasslab-v2/shared-artifacts
```

Both agent runtimes point at the exo OpenAI-compatible service at
`192.168.1.17:52415`. The cabled exo pair is `.17` and `.18`.

OpenCode currently supplies the inner agent loop. Hermes Agent is being
evaluated as a replacement for the OpenCode runtime/API integration and
possibly the Discord transport. It is not approved as a replacement for the
Glasslab state machine, evaluation contracts, artifact provenance, or
`workflow-api`.

## Latest Implemented Changes

The deployed research-orchestrator image corresponds to commit `624de3d` and
includes:

- a fresh methodology revision budget after new cluster evidence requires
  repair
- deterministic preflight rejection when workload source does not reference a
  contract-required artifact
- rejection of duplicated internal and outer multi-seed axes
- prompt guidance distinguishing internal stability trials from independent
  cluster repetitions

The orchestrator test suite passed 98 tests for that release. GitHub CI passed.

PR #91 merged the root `AGENTS.md` and current Discord/operator documentation.
This summarized handoff and the issue-backed work queue are follow-up changes
on branch `docs/contributor-agent-handoff`; do not treat them as merged until
their follow-up pull request is on `main`.

GitHub Issues are the authoritative work queue. The active backlog was reset
on 2026-08-06: obsolete OpenClaw, WhatsApp, literature, and old autoresearch
issues were closed with their history preserved. Current work is indexed in
`TODO.md`.

## Current Research Runs

### Adult Income

Run `cce710ceef97441685c777c8f19c767b` reached `COMPLETE`, including final
acceptance. It is the current completed end-to-end compatibility example.

### Wine Clustering

Run `39101d9c9d3d4753bcd74e93e6106819` is `TIMED_OUT` at turn 20.

What happened:

1. The initial matrix incorrectly expanded ten internal stability seeds into
   ten outer cluster jobs.
2. Workload calculations completed, but the evaluator rejected the results
   because `plots/clusters.png` was absent.
3. Honeydew identified the missing evidence.
4. Beaker added a deterministic PCA cluster plot using Matplotlib's
   noninteractive backend.
5. Beaker proposed a corrected matrix with one outer job and seed `17`.
6. Live deterministic preflight passed with no errors.
7. The overall run deadline expired before Honeydew could review the final
   proposal and expose execution approval.

No corrected Wine job was submitted. The implementation and final proposal
remain preserved in the timed-out run workspace. Terminal runs cannot currently
be resumed through `/research-resume`.

### Fashion-MNIST

The compatibility task is preflight-ready but has not completed a live run.

## Immediate Continuation

Do not restart Wine from protocol drafting. First implement a controlled retry
or clone-from-terminal-checkpoint operation that:

- creates a new durable run and runtime budget
- copies only approved protocol, task binding, worktree checkpoint, and latest
  valid pending proposal
- records lineage to the terminal parent run
- invalidates stale pending actions
- resumes at deterministic preflight and Honeydew methodology review
- never silently submits a job or bypasses human approval

Then use that path to continue the preserved one-job Wine proposal through
Honeydew review, Discord execution approval, one corrected cluster job,
evaluation, report, and final acceptance.

## Known Risks

- One orchestrator replica and SQLite WAL remain a scaling limitation.
- Agent turns can be slow against the shared exo model; large evidence bundles
  amplify the problem.
- Terminal checkpoint retry is missing (tracked in #92).
- Complete structured turns do not have a first-class read-only HTTP endpoint
  (tracked in #95).
- OpenCode runtime caches consume substantial shared storage per run (tracked
  in #99).
- A generic arbitrary-dataset run has not yet completed end to end (tracked
  in #98).
- OpenCode's package/model cache is now shared across runs instead of
  copied per run, and terminal-run scratch space (worktrees, runtime/) is
  eligible for cleanup after `terminal_run_retention_days`; see
  `services/research-orchestrator/scripts/cleanup-run-storage.py`. Hermes's
  own runtime storage does not yet have the same cache-sharing treatment
  (its on-disk layout under `HERMES_HOME` is not cleanly split into
  cache/data/state the way OpenCode's is), only cleanup.

Update this file whenever the active deployment, current blocker, or next legal
workflow step materially changes. Keep historical detail in dated docs or run
records rather than allowing this handoff to grow indefinitely.
