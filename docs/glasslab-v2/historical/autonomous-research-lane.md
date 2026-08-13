# Autonomous Research Lane

This note records the current bounded path for unattended background research work.

The goal is not free-form autonomy.

The goal is:

- keep cluster capacity busy when no user-submitted work is waiting
- preserve strict priority for future user-submitted jobs
- keep every stage inside explicit backend-owned records and validation

## Current corpus posture

For now, the literature path should stay on a controlled corpus.

That means:

- approved-source planning remains bounded by the seed manifest and approved-source rules
- queued papers should be fetched, stored, and interpreted only after they enter the explicit paper-intake queue
- do not widen the system to open-ended internet search until the controlled paper-getter and paper-understander path is reliable

This is intentional.

The current priority is:

- integrate the controlled corpus path end to end
- make interpretation produce useful literature-state and gap summaries from stored documents
- only then consider broader retrieval

## Current lane shape

The newer state boundary above this lane is the research session:

- a research session is the persistent literature workspace
- sessions hold the current goal and track the latest problem, queue,
  source document, intake, interpretation, assessment, design, and run
- this lets OpenClaw talk about literature work as an ongoing session instead
  of pretending every step is a separate workflow family

1. source scouting and paper pulling
   - `intake-agent` owns the approved-source manifest
   - the paper-harvester surface exposes:
     - `GET /paper-harvester/tracks`
     - `GET /paper-harvester/papers`
     - `POST /paper-harvester/plan`
     - `POST /paper-harvester/plan-from-problem`
   - `workflow-api` now exposes a persistent paper-intake queue:
     - `POST /paper-intake-queues/from-research-problem`
     - `GET /paper-intake-queues`
     - `GET /paper-intake-queues/latest`
     - `POST /paper-intake-queues/{queue_id}/stage-next-intake`
     - `GET /source-documents`
   - this lets literature candidates accumulate in the background before the
     later paper-understanding stages are triggered
   - staging a queued paper now creates a `SourceDocumentRecord` so the later
     understanding stage can consume stored PDFs/webpages instead of only raw URLs

2. intake normalization
   - `workflow-api` can call `intake-agent`
   - approved-source warnings remain bounded and explicit

3. workflow-family ordering
   - `workflow-api` can call the bounded ranker on `.12`
   - ranking only reorders an already-approved candidate set
   - ambiguous scores fail closed back to deterministic ordering

4. stage interpretation
   - `workflow-api` can call the live `interpretation-agent`
   - deterministic fallback remains available
   - interpretation now produces:
     - literature-state summary
     - research gaps
     - bounded experiment ideas
   - those outputs now flow into assessment and design instead of stopping at paper understanding

5. assessment and design
   - `assessment-agent` now consumes the interpretation outputs as advisory context
   - `design-agent` now carries literature-state and bounded experiment ideas into design notes
   - later stages no longer ignore what the paper-understander learned

6. execution readiness
   - `workflow-api` now exposes execution preflight per workflow family
   - run submission now checks that preflight before accepting the run
   - Kubernetes runner Jobs now actually receive the registry-declared resource requests, limits, and node selector

7. unattended digest execution
   - `workflow-api` stores digest schedules
   - `workflow-api` now exposes a bounded due-digest execution path
   - `schedule-worker` calls that path as the first unattended backend worker

## What this already enables

- a source-scout agent can ask for approved tracks and seed papers
- a future paper-puller can build a bounded fetch queue without inventing sources
- a research problem can now create a durable queue of candidate papers before deeper interpretation work starts
- paper understanding now produces explicit literature-state, gap, and bounded experiment summaries that downstream stages use
- execution readiness is now an explicit backend check instead of an implicit assumption
- intake routing can use the advisory ranker without surrendering authority
- unattended digest work can happen without OpenClaw becoming the hidden scheduler

## What is still intentionally missing

- autonomous creation of arbitrary jobs
- autonomous widening of workflow scope
- direct OpenClaw scheduling of background execution
- user-priority queueing and preemption logic

## Scheduling model

The intended long-term model is still:

- user-submitted jobs: highest priority
- autonomous research jobs: opportunistic / backfill only

That priority policy should be implemented at the backend scheduling layer, not in prompts.
