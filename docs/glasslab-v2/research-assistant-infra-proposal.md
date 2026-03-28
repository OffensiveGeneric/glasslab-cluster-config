# Research Assistant Infra Proposal

This note proposes the infrastructure and control-surface changes most likely to get Glasslab closer to the actual product vision:

- a human starts from a research idea in natural language
- the system preserves session context over time
- the system gathers and interprets literature
- the system proposes bounded experiments
- the system runs those experiments on lab infrastructure
- the system records results and suggests explicit next steps

The goal is not "make OpenClaw smarter."
The goal is "move responsibility into the layers that can actually be reliable."

## What Today Proved

The current backend direction is mostly right:

- research sessions are the right primary object
- skills are the right bounded stage surface
- execution templates are the right cluster-facing abstraction
- `workflow-api` is the right system-of-record for the research loop

The current front-door strategy is the weak point:

- OpenClaw is still being asked to route intent
- OpenClaw is still being asked to decide whether to touch the backend
- OpenClaw is still being asked to sequence or recover backend actions
- OpenClaw is still being asked to classify failures accurately

That is too much responsibility for the least reliable layer in the stack.

## Design Rule

The LLM should not be the workflow planner for the critical research loop.

The LLM should be used for:

- conversation
- summarization
- literature interpretation
- experiment explanation
- bounded next-step proposals

The platform should own:

- intent dispatch for common research actions
- session bootstrap
- literature-search orchestration
- progress tracking
- experiment execution
- artifact collection
- run comparison

Short version:

- backend decides
- LLM explains

## Proposed Target Stack

### 1. Deterministic Intent Router In Front Of OpenClaw

Add a narrow pre-router for a small set of high-value, high-frequency intents.

This should match obvious requests such as:

- start research session
- start literature search
- next paper
- summarize current literature
- propose next experiments
- run the current design

The router should not try to understand everything.
It should only intercept the small set of intents where the current OpenClaw path is clearly unreliable.

If a message matches one of those intents:

- call the backend action directly
- persist the result
- hand the result to OpenClaw only for phrasing

If a message does not match:

- let OpenClaw handle it conversationally

This preserves a natural-language experience without forcing the LLM to act as the API dispatcher.

### 2. One-Shot Backend Actions For The Research Loop

The current session/skills surface is good as an internal model, but the user-facing action surface should become more opinionated.

First-class backend actions should include:

- `start-literature-search`
- `advance-literature-review`
- `stage-next-paper`
- `summarize-session-literature`
- `propose-next-bounded-experiments`
- `prepare-current-design-for-run`
- `run-current-design`

Each action should:

- accept one narrow request
- own the orchestration internally
- create or update one `OperationRecord`
- return immediately with durable status information

That keeps the workflow legible while removing multi-step planning pressure from OpenClaw.

### 3. Background Job Boundary For Slow Research Work

Slow steps should stop living only in the request path.

Candidate background work:

- literature harvest
- source document fetch
- PDF/text extraction
- interpretation generation
- design generation
- evaluation/report generation

Recommended shape:

- `workflow-api` accepts the request
- `workflow-api` creates an `OperationRecord`
- the operation is published to a queue or worker lane
- a bounded worker updates status back into the session

This likely means the platform should finally make real use of:

- `NATS` for task/event dispatch
- a bounded worker process per stage family

That is a much better fit for "search for papers, this may take a minute" than the current silent request/timeout loop.

### 4. Session Memory As A First-Class Durable Workspace

Research sessions already exist and are now durable.
They should become the actual long-lived research workspace.

A session should persist:

- goal and scope
- paper queue
- source document references and extracted text locations
- literature summaries
- working notes
- decision log
- experiment ideas
- designs
- runs
- comparisons
- recommended next steps

This means the system can participate in a real research conversation over time instead of re-deriving context every turn.

### 5. Explicit Progress And Activity Feeds

The user should not have to guess whether the system is thinking, stuck, or broken.

Add a durable session activity feed driven by operations:

- `queued`
- `running`
- `waiting-on-fetch`
- `papers-found`
- `paper-ingested`
- `interpretation-ready`
- `design-ready`
- `run-submitted`
- `run-complete`
- `comparison-ready`

OpenClaw should be able to read that feed and say:

- "I started the literature search and found two candidate papers."
- "I am still fetching the first PDF."
- "The queue is thin; the current corpus match is weak."

This is much closer to a real research assistant than waiting 90 seconds and then blaming the API.

### 6. Execution Templates As Coarse Lab Job Shapes

Workflow families should stay coarse infrastructure shapes, not topic labels.

Target execution template set:

- `cpu-experiment`
- `gpu-experiment`
- `replication-run`
- `repo-scaffold`

Research topics like:

- forged art detection
- computer vision benchmark design
- alternate loss functions

should live in the session and design records, not in the workflow-family taxonomy.

That keeps the cluster contract stable while letting the research content vary freely.

### 7. GPU Infrastructure That Matches Real Research Work

The GPU path should support more than one narrow neural-net story.

The `gpu-experiment` lane should be treated as a general bounded research-execution substrate for:

- computer vision
- ML baselines
- neural nets
- ablation studies
- loss-function comparisons
- augmentation comparisons

That requires:

- one or more maintained GPU runner images
- explicit runtime contracts for `torch`, `torchvision`, CV dependencies, and dataset layout
- durable run artifacts
- preflight checks that report what is missing without pretending the topic is unsupported

### 8. Split Inference Responsibilities By Job

Do not require one model/runtime path to do everything.

The stack should support different inference lanes:

- chat shell model for OpenClaw
- interpretation/synthesis model for backend stage work
- optional stronger model for experiment proposals or literature summaries

This reduces pressure on the operator shell and makes it easier to swap or test better models without entangling the whole control plane.

### 9. Provenance And Live-State Introspection Everywhere

The platform should make it easy to answer:

- what code is live
- what runtime was exported
- what model/provider is serving
- where session state is stored
- what operation is currently running

This work has already started with provenance reporting.
It should continue until a broken turn can be debugged from one live check instead of a multi-hour forensic session.

## Proposed Infrastructure Changes

The following concrete changes would move the platform closest to the research-assistant vision.

### Near-Term

- add a deterministic session/literature intent router
- add one-shot backend actions for the core research loop
- use `OperationRecord` plus session activity feed for user-visible progress
- move slow literature/intake/interpretation work onto workers instead of request-only paths
- keep OpenClaw on a narrow tool surface and stop treating it as the workflow brain

### Medium-Term

- move durable session metadata from JSON to Postgres
- move source-document blobs and extracted text to MinIO or another explicit object store
- make NATS-backed workers real for literature, interpretation, and evaluation stages
- harden the `gpu-experiment` lane for CV and ML workloads
- add deterministic comparison and next-step proposal records to the session

### Later

- use larger models where synthesis quality matters
- keep command-mode or deterministic routing even if the chat model improves
- let backend stage agents improve literature understanding and experiment quality after the loop itself is already dependable

## What Not To Do

Do not:

- ask OpenClaw to plan the whole research workflow on the fly
- create a workflow family for each research topic
- hide multi-step orchestration inside prompts
- treat model size as the primary fix for orchestration problems
- let the operator shell become the source of truth for workflow state

## Closest Realistic Product Vision

If the infra changes above land, the user experience can still feel close to the original "ask to answer" vision:

1. the user says what they want in natural language
2. a deterministic router recognizes the action
3. the backend starts the session or advances the research loop
4. the user sees explicit progress and durable session state
5. the LLM interprets, summarizes, and helps decide what to try next
6. bounded experiments run on the cluster and return artifacts to the same session

That is still a research assistant.

It is just not "LLM improvises everything."
It is "LLM at the edge, deterministic backend in the middle, bounded execution underneath."

That is the version most likely to work in this lab.
