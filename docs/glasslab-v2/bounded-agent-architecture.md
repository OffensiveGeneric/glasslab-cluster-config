# Bounded Agent Architecture

This note describes the likely path forward if Glasslab keeps OpenClaw as the front door but stops depending on general live tool orchestration as the main execution model.

This is the likely path past the current `tool_choice` limitation.

## Why This Exists

Glasslab wants to move toward:

`paper or idea -> bounded validation experiment -> artifacts -> evaluation -> report`

The current local OpenClaw + vLLM + Qwen path is good enough for:

- intake
- summarization
- narrow no-arg tool selection

It is not yet good enough for:

- broad argumented tools
- live multi-tool chaining
- trusting the model as the main owner of workflow structure

So the next move should not be "make the operator agent do everything."

The next move should be:

- keep OpenClaw narrow
- move stage logic into explicit backend-owned agents/services
- let each bounded agent do one narrow job

## What To Borrow From AutoResearchClaw

Useful ideas to steal:

- one human-facing entrypoint
- explicit staged workflow
- specialized subsystems for different roles
- strong artifact discipline
- a custom pipeline behind the front door

What not to copy blindly:

- the assumption that a single autonomous run should go all the way to paper by default
- the assumption that dynamic multi-tool autonomy is already reliable enough locally
- the assumption that all workflow structure belongs in one generalized agent loop

The useful lesson is:

- the impressive behavior comes from a coherent staged pipeline, not from "chat plus random tools"

## Core Rule

OpenClaw is the front door.
It is not the stage orchestrator of record.

The orchestrator of record should remain backend-owned:

- `workflow-api`
- workflow registry
- evaluator
- reporter
- explicit stage-state persistence

## Proposed Glasslab Bounded Agents

These do not need to be "agents" in a mystical sense.

They can be:

- backend endpoints
- queue workers
- deterministic template engines with optional LLM assistance
- small services that use a model only for one bounded transformation

### 1. Intake Agent

Input:

- paper reference
- notes
- plain-language research goal

Output:

- normalized intake record
- source references
- short scope summary
- initial workflow-family candidates

What should be deterministic:

- intake record schema
- persistence
- required fields

What may use an LLM:

- summarization
- initial classification hints

### 2. Design Agent

Input:

- normalized intake record

Output:

- bounded design draft
- proposed approved workflow family
- declared inputs
- candidate resource profile
- expected artifacts

What should be deterministic:

- workflow-family allowlist
- approval-tier checks
- resource-profile allowlist

What may use an LLM:

- extraction from paper text or notes
- shaping ambiguous intent into a draft

### 3. Execution-Prep Agent

Input:

- approved design draft

Output:

- canonical run manifest
- backend submission request

What should be deterministic:

- manifest schema
- runner image selection
- policy validation
- job submission boundary

What may use an LLM:

- ideally nothing essential

### 4. Evaluation Agent

Input:

- completed run bundle or multiple run bundles

Output:

- operator-facing evaluation summary

What should be deterministic:

- comparisons
- rankings
- metric aggregation

What may use an LLM:

- only summary/explanation after deterministic comparison already exists

### 5. Reporting Agent

Input:

- manifest
- metrics
- evaluator output

Output:

- human-facing memo
- concise operator summary

What should be deterministic:

- report structure
- required sections
- artifact references

What may use an LLM:

- optional prose polishing or explanation

### 6. Literature Agent

Input:

- paper corpus
- extracted notes

Output:

- literature notes
- extracted claims
- method summaries
- unresolved questions

What should be deterministic:

- source tracking
- citation storage
- artifact format

What may use an LLM:

- extraction and summarization

## Stage Ownership

Recommended ownership model:

- OpenClaw:
  - receives requests
  - triggers stage transitions
  - summarizes results
- `workflow-api`:
  - owns state machine
  - persists stage records
  - validates transitions
  - triggers bounded execution
- bounded agents/services:
  - produce stage-specific outputs
  - do not own overall policy
- evaluator/reporter:
  - own deterministic post-run processing

## What The Operator Should Actually Trigger

The operator shell should expose a small number of no-arg or near-no-arg transitions, such as:

- start intake
- get latest intake
- create design draft from latest intake
- create validation run from latest design
- fetch latest run summary
- generate comparison summary
- generate report summary

These are not broad free-form tools.

They are explicit workflow transitions.

## Why This Is Better Than Waiting For Perfect Tool Use

This approach avoids three current problems:

1. the model does not have to reliably generate structured control payloads for every step
2. OpenClaw does not need rich multi-tool control from the first day
3. workflow state lives in backend records, not chat history

## How Multi-Agent Behavior Still Happens

Glasslab can still become meaningfully multi-agent under this model.

The difference is:

- each agent is bounded
- each stage has explicit inputs and outputs
- orchestration remains legible

So "multi-agent" becomes:

- literature agent produces notes
- design agent produces draft
- execution-prep agent produces manifest
- evaluation agent produces summary
- reporting agent produces memo

That is safer than one generic agent improvising all of those roles live.

## Recommended First Implementation Shape

Do not start by adding many OpenClaw tools.

Start by adding backend records and transitions for:

1. intake
2. design draft
3. validation run from design draft

Then let OpenClaw trigger those through narrow no-arg tools.

This will produce the first real "paper to validation experiment" path without needing broad argumented tool reliability.

## When To Revisit Richer Tool Orchestration

Revisit broader tool surfaces only after at least one of these is true:

- the reachable OpenClaw operator path exposes `tool_choice`
- a stronger local model proves reliable on the same harness
- the backend transition model is stable enough that richer tool calls are low-risk

## What A Deep Research Review Should Evaluate

If this architecture is reviewed externally, the useful questions are:

1. Which stage boundaries should be deterministic versus LLM-assisted?
2. Which bounded agents should be separate services versus functions inside `workflow-api`?
3. What minimal state machine best supports paper -> design draft -> validation run?
4. What artifacts should each stage be required to emit?
5. Which parts of AutoResearchClaw's staged system are worth reproducing in Glasslab, and which depend on assumptions Glasslab does not share?

## Bottom Line

If OpenClaw cannot yet reliably drive multi-tool workflows through the current control surface, the right answer is not to abandon the goal.

The right answer is to move the real workflow into bounded backend agents/services and let OpenClaw remain the narrow shell in front of them.
