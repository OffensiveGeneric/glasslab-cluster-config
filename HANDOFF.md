# Glasslab Current Handoff

Last updated: 2026-08-06

This is the compact current-state checkpoint for switching human or coding
agents. Read `AGENTS.md` first for stable rules and architecture. Read
`TODO.md` for the prioritized work queue.

## Current Direction

The active research path is:

```text
Discord
  -> research-orchestrator
  -> Honeydew and Beaker agent runtimes
  -> workflow-api
  -> bounded Kubernetes Jobs
  -> immutable evaluation and artifacts
```

Honeydew owns protocol, methodology review, evidence verification, and the
final report. Beaker owns implementation, experiment proposals, and result
analysis. The orchestrator, not either model, owns state transitions,
approvals, policy, job submission, and durable records.

OpenCode currently supplies the inner agent loop. Hermes Agent is being
considered as a replacement for the custom OpenCode runtime/API integration
and possibly the Discord transport. It is not approved as a replacement for
the Glasslab state machine, evaluation contracts, artifact provenance, or
`workflow-api`.

## Authority And Access

- GitHub is committed state.
- The provisioner at `192.168.1.44` is the canonical live checkout and cluster
  operations host.
- Actual live state must be checked from the provisioner; laptop state and docs
  alone are insufficient.
- Canonical checkout on the provisioner:
  `/home/glasslab/cluster-config`.
- Normal access aliases are `glasslab-gateway` and `glasslab-provisioner`.
- Cluster workers are not normal contributor login targets.

The research orchestrator is a single pod on `node05`. Its state and per-run
workspaces are on `glasslab-shared-artifacts`, backed by NFS at
`192.168.1.207:/volume1/backup/glasslab-v2/shared-artifacts`.

Both agent runtimes are configured to use the exo OpenAI-compatible service at
`192.168.1.17:52415`. The cabled exo pair is `.17` and `.18`.

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

Documentation work is in PR #91 on branch
`docs/contributor-agent-handoff`. It adds `AGENTS.md`, this handoff, `TODO.md`,
and updates the current Discord/operator documentation. Do not treat it as
merged until GitHub confirms it is on `main`.

GitHub Issues are again the authoritative work queue. The active backlog was
reset on 2026-08-06: obsolete OpenClaw, WhatsApp, literature, and old
autoresearch issues were closed with their history preserved. Current work is
indexed in `TODO.md` and tracked in issues #92 through #102.

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

## Inspect Live State

From a contributor workstation:

```bash
ssh glasslab-provisioner
sudo -n env KUBECONFIG=/home/glasslab/.kube/config \
  kubectl -n glasslab-v2 get pods,jobs -o wide
```

For the internal orchestrator API, create a tunnel:

```bash
ssh -L 18080:127.0.0.1:18080 glasslab-provisioner \
  'sudo -n env KUBECONFIG=/home/glasslab/.kube/config \
   kubectl -n glasslab-v2 port-forward \
   svc/glasslab-research-orchestrator 18080:8080'
```

Then:

```bash
RUN=39101d9c9d3d4753bcd74e93e6106819
curl -fsS "http://127.0.0.1:18080/runs/$RUN" | jq
curl -fsS "http://127.0.0.1:18080/runs/$RUN/events" | jq
curl -fsS "http://127.0.0.1:18080/runs/$RUN/artifacts" | jq
```

Per-run files are available inside the orchestrator pod at:

```text
/mnt/artifacts/research-orchestrator/runs/<run-id>/
```

## Known Risks

- One orchestrator replica and SQLite WAL remain a scaling limitation.
- Agent turns can be slow against the shared exo model; large evidence bundles
  amplify the problem.
- Terminal checkpoint retry is missing.
- Complete structured turns do not have a first-class read-only HTTP endpoint.
- OpenCode runtime caches consume substantial shared storage per run.
- Discord has no explicit list or status slash command; the editable thread
  message is the normal status surface.
- A generic arbitrary-dataset run has not yet completed end to end.

Update this file whenever the active deployment, current blocker, or next legal
workflow step materially changes. Keep historical detail in dated docs or run
records rather than allowing this handoff to grow indefinitely.
