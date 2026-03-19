# No-Arg Vs Argumented Tools

This note exists to keep Glasslab focused on the real goal:

`paper or research idea -> bounded validation experiment -> artifacts -> evaluation -> report`

The question is not "how do we make the model feel more autonomous?"

The question is "what tool shape gets us from intake to approved execution with the least fragility?"

## What No-Arg Tools Are Buying Us

The current no-arg operator tools work because they keep the model out of the brittle part.

The model only needs to:

- decide which narrow tool to use
- summarize the result

The repo and backend provide the important structure:

- the request payload
- the workflow family
- the approval assumptions
- the backend call shape
- the expected artifact contract

That is why the current safe path works:

- `workflow_api_create_validation_run`
- `workflow_api_get_last_validation_run`

The model is not being asked to synthesize structured arguments correctly.

## What Argumented Tools Would Buy Us

If argumented tools were reliable, they would reduce wrapper sprawl and make the operator path more expressive.

They would help with things like:

- selecting one workflow by exact ID
- choosing a bounded resource profile
- choosing among approved datasets
- requesting a narrow read query without adding a one-off wrapper tool

That is useful.

But it is only useful if the argument generation is measurably reliable.

## What The Current Failure Actually Means

The current experimental read-only tool:

- `workflow_api_get_family_by_id`

requires only one argument:

- `workflow_id`

Even that tiny schema failed under the current local OpenClaw + vLLM + Qwen path.

So the current conclusion is simple:

- no-arg tool selection is usable
- argument generation is not yet trustworthy

This does not mean Glasslab is pointed in the wrong direction.
It means the safe autonomy boundary is still mostly "choose among pre-shaped actions," not "generate structured control payloads freely."

## What This Means For The Real Goal

The real goal is not "argumented tools everywhere."

The real goal is:

1. intake a paper or research goal
2. classify it into an approved workflow family
3. produce a bounded experiment plan
4. submit approved execution
5. evaluate and report deterministically

That can still be achieved with mostly no-arg tools if the backend is shaped correctly.

In practice, that means:

- the model can classify and summarize
- the backend can hold approved workflow templates
- the backend can derive canonical manifests
- the backend can reject anything out of policy

This is still autonomous work.
It is just autonomy built on controlled rails instead of free-form structured generation.

## Should Glasslab Split More Services Or Tools?

Maybe, but only when the split reduces ambiguity at the system boundary.

Good splits:

- a workflow registry that owns allowed workflow families
- an evaluator that owns deterministic comparisons
- a reporter that owns deterministic output formatting
- narrow OpenClaw tools that map cleanly onto those services

Bad splits:

- adding many tiny tools just to feel agentic
- pushing workflow structure into prompt glue
- making the model choose among too many overlapping tools

Splitting services can help.
Splitting tools only helps if each tool has a clear contract and low ambiguity.

## Why The Current Tooling Still Makes Sense

The current direction is defensible because:

- OpenClaw is staying narrow
- `workflow-api` is holding the execution contract
- the workflow registry is explicit
- evaluator and reporter can stay deterministic
- no-arg tools give a reliable first operator path

This is not a dead end.
It is the stable base layer.

## What Larger Models Might Change

A larger or better local model may improve:

- argument filling
- schema adherence
- tool choice consistency

That could make bounded argumented tools practical later.

But even if that happens, the architecture should still assume:

- backend validation is mandatory
- allowed workflows stay explicit
- high-impact actions should stay tightly bounded

A larger model may widen the safe frontier.
It should not redefine the control model.

## Recommended Operating Policy

For now:

- keep no-arg tools as the production operator path
- add argumented tools only for low-risk, bounded reads
- promote argumented tools only after they pass repeated harness validation
- prefer backend-owned templates over model-synthesized execution payloads

## Decision Test

When a new idea comes up, ask:

1. Does this reduce friction from paper to validation experiment?
2. Does it keep workflow rules explicit and reviewable?
3. Does it reduce operator ambiguity instead of increasing it?
4. Can it fail safely if the model emits bad structure?

If the answer to those is not clearly yes, it is probably not the next thing to build.
