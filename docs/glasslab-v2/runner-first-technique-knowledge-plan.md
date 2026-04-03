# Runner-First Technique Knowledge Plan

This note captures the current priority reset for Glasslab v2.

The near-term goal is not to build the most flexible research assistant. It is
to build the most useful bounded experiment-runner we can, as quickly as
possible.

## Priority

The product should now optimize for:

- turning a problem statement or manually added source into a bounded method spec
- launching multiple approved methodology variants
- comparing results deterministically
- persisting keep/discard/review decisions
- continuing bounded method exploration while operators are away

The key value proposition is:

- trying more methodologies than humans have time or patience to try manually
- preserving the evidence for what worked and what failed

## Technique Knowledge Stance

We already have a large amount of methodology knowledge curated in NotebookLM.
That is useful, but the fastest path is not to wait for a deep NotebookLM
integration.

For now, the correct posture is:

- use NotebookLM as a knowledge-authoring and synthesis tool
- export technique knowledge from it in a bounded structured format
- import that structure into Glasslab-owned records
- let the runner consume those records

In other words:

- NotebookLM helps us build the corpus
- Glasslab owns the execution contract

## Fastest Path

The fastest practical path is:

1. define a narrow technique-catalog format
2. manually export technique knowledge from NotebookLM into that format
3. import it into `workflow-api`
4. let interpretation and autoresearch draw from it
5. keep the runner consuming only bounded `MethodSpec` objects

This is less elegant than a live "ask the oracle" loop, but it is much more
likely to get the system useful soon.

## Why Not Start With A NotebookLM Oracle

That path is attractive, but it is not the immediate priority.

A direct NotebookLM-backed planner would introduce:

- another runtime dependency
- another latency source
- another failure mode
- another place where execution-relevant knowledge becomes hard to audit

That may be worth doing later. It is not the fastest route to a useful
experiment-runner.

## Practical Knowledge Boundary

Technique knowledge should be imported into Glasslab as structured facts like:

- task types
- model families
- algorithm names
- losses and distance objectives
- metrics
- split and validation strategies
- baseline families
- required Python packages
- GPU requirements
- resource-profile hints
- workflow-template compatibility
- common failure modes
- source references

That knowledge should feed:

- interpretation
- methodology drafting
- preflight checks
- autoresearch mutation choices
- comparison summaries

It should not directly produce arbitrary manifests or code execution.

## Execution Boundary

The runner should continue to operate on this narrower chain:

- `SourceDocument`
- `TechniqueKnowledge`
- `MethodSpec`
- approved workflow run

This keeps broad methodology knowledge available while preserving a bounded
execution surface.

## Current Product Direction

Near-term product direction:

- experiment-runner first
- manual source add is acceptable
- interpretation should become more bounded and workflow-ready
- `!run` and `!launch-iteration` should be reliable
- autoresearch should explore multiple bounded methodology variants in parallel

De-prioritized for now:

- broad autonomous literature search
- broad UX work
- more OpenClaw cleverness
- deeper external-oracle integration before the runner is useful

## Concrete Next Steps

1. add a `TechniqueCatalog` schema and persistence path in `workflow-api`
2. add a JSON import format for NotebookLM-derived technique cards
3. make interpretation query that catalog when building `TechniqueKnowledge`
4. make autoresearch mutation logic draw from the same catalog
5. make parallel methodology launch a first-class campaign action

The standard for progress should be simple:

- does this make the bounded experiment-runner more useful soon?

If not, it is probably not the current priority.
