# Model Improvement Options

This note exists to separate several ideas that are easy to blur together:

- stronger main model
- ranker / reranker
- retrieval improvements
- control-surface improvements
- backend decomposition

These are not the same thing.

They solve different parts of the current Glasslab bottleneck.

## Current Situation

The current local path is:

- OpenClaw
- local vLLM
- `Qwen/Qwen3-4B-Instruct-2507`
- narrow custom `workflow-api` tools

What currently works:

- no-arg tool selection
- intake and summary behavior
- narrow state-changing tool triggers

What does not work reliably:

- tiny argumented tools
- trustworthy structured tool arguments
- rich live multi-tool behavior

So the current problem is not simply "the model is down" or "the model is useless."

The real problem is:

- the model is not strong enough to be trusted broadly for structured control
- and the reachable OpenClaw control surface does not expose the tool-choice control that would make experiments cleaner

## 1. Stronger Main Model

### What it means

Replace the current local main model with a stronger one that still fits your hardware and runtime constraints.

### What it may improve

- better schema adherence
- better tool-choice consistency
- better argument filling
- better extraction and summarization quality

### What it does not automatically fix

- missing `tool_choice` exposure in the reachable OpenClaw gateway path
- backend policy gaps
- poor workflow decomposition

### Current hardware reality

The most plausible place to try this is still `node02`.

What is realistic:

- another model in roughly the same class
- a modestly larger quantized model
- context-length tradeoffs to fit a somewhat stronger model

What is not likely to be easy:

- a dramatic leap to a much stronger model tier with boring production ergonomics

## 2. Ranker / Reranker

### What it means

Use a dedicated model or scoring stage to choose among already-generated candidates.

Examples:

- workflow-family ranking
- literature-snippet reranking
- design-draft candidate ranking
- comparison-set selection

### What it may improve

- reduces ambiguity before execution
- makes candidate selection more reliable than a single free-form generation step
- gives the backend a confidence threshold to accept or reject

### What it does not automatically fix

- live tool-calling argument generation
- OpenClaw gateway control-surface limitations

### Why it fits Glasslab

This aligns well with the current backend-first architecture.

A good use pattern is:

1. backend or generator creates a small candidate set
2. ranker scores candidates
3. backend accepts top candidate if confidence is good enough
4. otherwise ask for clarification

This is a strong fit for:

- intake -> workflow-family mapping
- literature retrieval relevance
- design-draft selection

## 3. Retrieval / RAG Improvements

### What it means

Improve how the system finds:

- workflow definitions
- prior runs
- literature notes
- evaluation artifacts

### What it may improve

- better context for intake and design
- fewer hallucinated references
- better grounding for operator summaries

### What it does not automatically fix

- structured tool arguments
- missing `tool_choice`

### Why it still matters

Good retrieval can reduce pressure on the main model by making the right context easy to access.

## 4. Control-Surface Improvements

### What it means

Expose more precise control at the gateway/operator boundary.

Most important current example:

- expose `tool_choice` on the reachable OpenClaw operator path

### What it may improve

- clean single-tool experiments
- better separation of tool-selection problems from argument-generation problems
- later path toward more reliable multi-tool behavior

### What it does not automatically fix

- weak argument generation by the model itself

### Current status

This currently appears to require:

- an OpenClaw patch
- or a different OpenClaw build/version
- or another supported lower-level interface

It does not appear to be solvable from Glasslab runtime YAML alone.

## 5. Backend Decomposition

### What it means

Move more intelligence into bounded backend stages and records instead of asking one live chat model to improvise everything.

Examples:

- intake record
- design draft
- run derivation from design draft
- deterministic evaluation
- deterministic reporting

### What it may improve

- makes the overall system more reliable immediately
- reduces dependence on broad structured tool use
- makes stage transitions explicit and testable

### What it does not automatically fix

- main-model quality
- OpenClaw gateway limitations

### Why it is still probably the best near-term investment

This directly advances the core product goal:

- paper or idea -> bounded validation experiment

without waiting for perfect tool-calling.

## Where A Dedicated Ranker Makes The Most Sense

The strongest current Glasslab uses for a ranker would be:

### A. Workflow-Family Selection

Input:

- intake record
- small list of approved candidate workflow families

Output:

- ranked workflow-family candidates
- confidence score

This is likely the best first use.

### B. Literature Snippet Relevance

Input:

- a question or design draft
- retrieved paper/note chunks

Output:

- reranked supporting context

### C. Design-Draft Candidate Selection

Input:

- 2-5 backend-generated design candidates

Output:

- ranked design options

## What A Ranker Should Not Be Asked To Do

Avoid using a ranker as:

- the main orchestrator
- a replacement for backend validation
- a replacement for explicit approval tiers
- a magical fix for live multi-tool autonomy

## Recommended Priority Order

### 1. Backend decomposition

Build:

- intake
- design draft
- run from latest design

This gives immediate product movement.

### 2. Add ranking where candidate choice is the real problem

Best first target:

- workflow-family mapping from intake

### 3. Modestly improve the main model if hardware allows

Run a measurable comparison on `node02`.

### 4. Revisit richer tool-calling only after control-surface exposure improves

Especially:

- `tool_choice`

## Bottom Line

If Glasslab wants to improve the "AI" part of the system, it should not think only in terms of "bigger main model."

The more realistic improvement stack is:

- better backend stage structure
- ranking for bounded candidate selection
- modest main-model improvement
- better OpenClaw control exposure later

That is more likely to move the system toward useful autonomy than chasing broad live tool orchestration too early.
