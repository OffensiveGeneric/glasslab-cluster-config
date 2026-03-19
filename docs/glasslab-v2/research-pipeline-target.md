# Glasslab Research Pipeline Target

This file exists to stop architectural drift.

When a new idea shows up, compare it to this target before adding more moving parts.

## Why This Exists

The closest external shape to what Glasslab is trying to become is something like AutoResearchClaw:

- one human-facing entrypoint
- a staged research workflow behind it
- explicit artifacts
- explicit approval boundaries
- operator-facing interaction through OpenClaw

That is the right direction.

What Glasslab should not do is copy that shape blindly without respecting the constraints of this lab.

## The Target Product Shape

The user experience we are aiming for is:

1. a human presents a research goal in plain language
2. the system maps that goal to an approved workflow family
3. the system plans and executes a staged workflow
4. each stage produces explicit artifacts
5. evaluation and reporting happen through deterministic backend services where possible
6. the operator sees progress, outputs, and approval checkpoints through a narrow gateway

Short version:

`message -> approved workflow -> staged execution -> artifacts -> evaluation -> report`

## What Glasslab Should Be

Glasslab should become:

- a controlled research workflow platform
- backed by Kubernetes Jobs and explicit services
- using Git-tracked workflow definitions
- with OpenClaw as the operator shell
- with deterministic backend services doing as much of the critical work as possible

Glasslab should not become:

- a bag of prompts glued together with hidden behavior
- a shell-access agent with cluster mutation powers by default
- an “autonomous” system that hides workflow rules inside model output

## The Core Design Rule

OpenClaw is the front door.
It is not the workflow brain.

The real workflow brain should live in:

- `workflow-api`
- `workflow-registry`
- evaluator and reporter services
- bounded Kubernetes execution paths

The LLM should help with interpretation, planning, extraction, summarization, and operator interaction.
It should not be the only place where workflow structure exists.

## The Intended End State

Glasslab should eventually support a top-level research workflow that feels like this:

### Stage 1: Intake

Input:

- plain-language research goal

Output:

- normalized research request
- initial scope summary
- declared requested workflow family

### Stage 2: Triage

Input:

- normalized request

Output:

- classification of request type
- approval tier
- decision on whether the request maps to an allowed workflow

### Stage 3: Research Design

Input:

- approved request

Output:

- structured experiment plan
- declared datasets
- declared models or methods
- expected artifacts
- success criteria

### Stage 4: Literature / Context Collection

Input:

- structured plan

Output:

- literature notes
- extracted method summaries
- references
- open questions

### Stage 5: Execution Planning

Input:

- experiment plan
- available cluster resources

Output:

- canonical run manifest
- job specification
- resource profile
- execution receipt

### Stage 6: Bounded Execution

Input:

- approved run manifest

Output:

- logs
- metrics
- intermediate artifacts
- final status

### Stage 7: Evaluation

Input:

- one or more completed runs

Output:

- deterministic comparison
- ranking
- selected candidate

### Stage 8: Reporting

Input:

- manifest
- metrics
- evaluation outputs

Output:

- operator-facing summary
- report memo
- exportable final artifact set

### Stage 9: Review / Approval

Input:

- report and outputs

Output:

- accept
- rerun
- revise
- reject

That is enough structure.
Do not invent a 20-plus-stage workflow unless it is actually buying clarity.

## The Glasslab Version Of “Autonomous”

Glasslab should use a narrow definition of autonomy.

Desired:

- the system can move through pre-approved stages without constant human handholding
- the system can generate the right artifacts and status updates automatically
- the operator can intervene at explicit boundaries

Not desired:

- silent tool expansion
- arbitrary shell execution
- hidden cluster mutations
- implicit workflow family changes
- unbounded self-modification

## What Must Stay Explicit

These things should remain Git-visible and reviewable:

- workflow family definitions
- approval tiers
- expected artifacts
- runner image choices
- dataset assumptions
- resource profiles
- tool policies
- chat-channel policies

If a critical behavior is only visible in a prompt, that is a design smell.

## What Should Be Deterministic

Prefer deterministic backend services for:

- validation
- workflow lookup
- manifest generation
- job submission
- run persistence
- artifact indexing
- evaluation
- reporting templates

Use LLMs for:

- request interpretation
- literature extraction
- summarization
- operator-facing explanation
- candidate design assistance

That split is important.

## What Should Stay Narrow In OpenClaw

OpenClaw should expose:

- approved internal API tools
- narrow read/write paths against declared backend services
- policy-constrained agent roles
- explicit channel bindings

OpenClaw should not expose by default:

- arbitrary shell access
- mutating `kubectl`
- unrestricted filesystem writes
- arbitrary outbound web access
- broad repo mutation powers

The current no-arg tool pattern is not a weakness.
It is the start of a safe operator surface.

## Artifact Contracts Matter

Every real workflow should produce a stable artifact set.

At minimum, Glasslab workflows should aim to produce:

- canonical run manifest
- config
- metrics
- logs
- status
- report
- artifact index

Optional workflow-specific artifacts are fine.
Undeclared mystery outputs are not fine.

## The Real Constraints Glasslab Must Respect

Unlike a purely software-first research agent repo, Glasslab is constrained by:

- `.44` still being operationally special
- local-secret handling outside Git
- imperfect image distribution
- no mature shared storage backend yet
- local model tool-calling reliability limits
- a real cluster with finite GPU and CPU capacity

Any future design that ignores these constraints is fantasy, not architecture.

## What To Build Next

If we want Glasslab to move toward this target cleanly, the next architectural step is:

- define one flagship end-to-end workflow family for `glasslab-v2`

That flagship workflow should:

- feel coherent from the operator side
- have explicit stages
- have explicit artifacts
- use deterministic backend services for control logic
- use the LLM where it adds value, not where it hides state

Possible first flagship workflow:

- `literature-to-experiment-to-report`

Meaning:

- start from a research prompt or paper set
- extract a structured experiment plan
- map that plan to approved execution families
- run bounded experiments
- evaluate results
- return a report bundle

## What To Avoid

Avoid these failure modes:

- adding more services before clarifying the canonical workflow
- adding more tools before stabilizing the safe operator path
- building around one-off prompts instead of workflow contracts
- pretending design docs equal live reliability
- widening trust boundaries just to make demos feel smoother

## Decision Test For New Ideas

When a new idea comes up, ask:

1. Does this make the flagship workflow clearer?
2. Does this keep OpenClaw as a gateway instead of a hidden brain?
3. Does this move logic into explicit backend contracts instead of prompts?
4. Does this preserve reviewability in Git?
5. Does this respect actual lab constraints?
6. Does this reduce or increase dependence on undocumented `.44` state?

If the answer is mostly no, the idea is probably noise.

## Short Statement Of Intent

Glasslab is trying to become:

- a controlled, staged, research workflow platform
- with explicit contracts
- explicit artifacts
- explicit approvals
- narrow operator interaction
- and infrastructure realistic enough to run on the actual lab cluster

That is the target.
