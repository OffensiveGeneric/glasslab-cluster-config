# Autonomous Research Lane

This note records the current bounded path for unattended background research work.

The goal is not free-form autonomy.

The goal is:

- keep cluster capacity busy when no user-submitted work is waiting
- preserve strict priority for future user-submitted jobs
- keep every stage inside explicit backend-owned records and validation

## Current lane shape

1. source scouting and paper pulling
   - `intake-agent` owns the approved-source manifest
   - the paper-harvester surface exposes:
     - `GET /paper-harvester/tracks`
     - `GET /paper-harvester/papers`
     - `POST /paper-harvester/plan`

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

5. unattended digest execution
   - `workflow-api` stores digest schedules
   - `workflow-api` now exposes a bounded due-digest execution path
   - `schedule-worker` calls that path as the first unattended backend worker

## What this already enables

- a source-scout agent can ask for approved tracks and seed papers
- a future paper-puller can build a bounded fetch queue without inventing sources
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
