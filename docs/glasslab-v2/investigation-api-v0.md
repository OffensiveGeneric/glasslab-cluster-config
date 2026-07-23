# Investigation API v0

Status: current first vertical slice

Date: 2026-07-23

## Purpose

Glasslab's product-level object is an **investigation**.

The run fabric remains the execution core: it validates registered workloads,
creates bounded Kubernetes Jobs, and stores runs and artifacts. An investigation
sits above that core and preserves why a run exists, what was fixed before it
ran, and which evidence supports a later claim.

An investigation currently owns:

- one research question
- an explicit exploratory or confirmatory mode
- versioned hypotheses, which may be added after the question is opened
- immutable plan-approval snapshots
- the runs launched from an approved plan
- claims linked to exact run artifacts

The existing `ResearchSessionRecord` remains the working context used by intake,
design, and command-routing code. Each investigation creates and owns one
underlying research session. This avoids a second execution path while the
operator surfaces migrate to investigation language.

## Current API

| Method and path | Effect |
| --- | --- |
| `POST /investigations` | Create an investigation and its underlying research session. |
| `GET /investigations` | List investigations. |
| `GET /investigations/latest` | Fetch the most recently changed investigation. |
| `GET /investigations/{investigation_id}` | Fetch the durable investigation record. |
| `GET /investigations/{investigation_id}/context` | Fetch the investigation, session, current and approved designs, and linked runs. |
| `POST /investigations/{investigation_id}/hypotheses` | Add a hypothesis under the mode-specific integrity rules. |
| `POST /investigations/{investigation_id}/plan-approvals` | Freeze the current runnable design and hypotheses by SHA-256. |
| `POST /investigations/{investigation_id}/runs` | Launch the exact active approved design through the existing run fabric. |
| `POST /investigations/{investigation_id}/claims` | Record a supported, refuted, or inconclusive claim with exact evidence references. |

Create an investigation:

```json
{
  "title": "Adult Income baseline investigation",
  "research_question": "Which bounded tabular baseline best predicts the Adult Income target without target leakage?",
  "research_mode": "exploratory",
  "hypotheses": [
    "A tree-based baseline will outperform logistic regression on the frozen holdout split."
  ],
  "priorities": [
    "leakage prevention",
    "subgroup analysis",
    "reproducibility"
  ]
}
```

`hypotheses` may be omitted when the researcher is still refining the question.
At least one hypothesis is required before a plan can be approved.

The response includes both `investigation_id` and `session_id`. Intake and plan
generation still use the current session endpoints in this slice:

```text
POST /research-sessions/{session_id}/intake
POST /research-sessions/{session_id}/transitions/prepare-current-plan
POST /investigations/{investigation_id}/plan-approvals
POST /investigations/{investigation_id}/runs
```

## Integrity Rules

### Plan freezing

A plan approval hashes a canonical JSON snapshot containing:

- investigation identity
- research mode
- research question
- all current hypothesis records
- the complete design draft

Launch recomputes the hash. If the design or hypothesis state changed after
approval, execution is rejected until the revised plan is approved.

The approval record retains the complete question, hypothesis records, and
design snapshot used to produce the hash. It also snapshots the design's
evaluator and budget contracts when they exist.

### Exploratory work

Exploratory investigations may add hypotheses after an approval. Doing so:

- keeps the prior approval in history
- clears the active approval
- returns the investigation to `planning`
- requires explicit re-approval before another run

This records that the research direction changed after prior work was visible.

### Confirmatory work

Confirmatory hypotheses are frozen after the first plan approval. A plan may be
revised and re-approved before execution, but it cannot be replaced after an
investigation run has begun.

### Evidence-backed claims

A claim must:

- reference hypotheses in the same investigation
- reference runs launched by that investigation
- reference artifacts already ingested for those runs
- use terminal runs

`supported` and `refuted` claims require successful runs. `inconclusive` claims
may also preserve evidence from failed or rejected terminal runs.

The caller supplies a run ID and artifact name. Glasslab resolves and stores the
artifact reference from the run record; callers cannot substitute an arbitrary
evidence URI.

This v0 establishes provenance, not independent scientific verification. Its
trust boundary is the current result-ingestion path: an artifact must be
ingested, but this slice does not inspect the artifact's contents or re-run the
reported calculation.

## What This Makes Real

The following path is now represented by durable control-plane records:

```text
question
  -> hypotheses
  -> current design
  -> explicit frozen approval
  -> bounded run
  -> ingested artifacts
  -> evidence-backed claim
```

This is deliberately layered over the existing registered-workload and
Kubernetes Job machinery. It does not introduce a new scheduler, runner, or
artifact store.

## Next Slices

This v0 does not yet provide:

- investigation-native source, dataset, and note intake routes
- an agent workspace that writes and versions novel experiment code
- solver/evaluator isolation for the benchmark task packs
- automatic claim extraction or evaluator verification
- a claim-to-evidence graph across multiple investigations
- investigation closeout and reproducibility-bundle generation
- command-router migration from `research-sessions` to `investigations`

The next useful vertical slice is an agent workspace contract that freezes code,
data references, environment, and execution command alongside the approved
plan. Adult Income can then serve as the first CPU acceptance workload; Wine
Clustering and Fashion-MNIST Contrastive can extend the same contract without
adding bespoke API families.
