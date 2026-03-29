# Research Assistant UX Boundary

This note exists because the last round of OpenClaw work made one thing painfully clear:

- a research assistant that cannot reliably start a research session or gather the first papers does not have a usable UX

The product problem is not just "tool calling is flaky."
The product problem is that the current front door is carrying too much responsibility.

## What We Learned

We spent disproportionate effort on the very first user action:

- "start a research session"
- "start a literature search"
- "help me investigate X"

That should have been the easiest part of the system.
Instead, it was the least reliable part.

This means the UX boundary is wrong.

## The Wrong Boundary

The wrong version of the product is:

- the user speaks naturally
- OpenClaw interprets intent
- OpenClaw decides whether to call the backend
- OpenClaw decides which tool or sequence to call
- OpenClaw interprets slow or failed work
- OpenClaw explains the result

That makes the conversational shell responsible for:

- intent routing
- control flow
- state inspection
- recovery logic
- error classification

This is too much.

## The Right Boundary

The right version of the product is:

- the user speaks naturally
- a deterministic layer recognizes a small set of high-value actions
- the backend performs the actual research-loop action
- OpenClaw explains what happened and continues the conversation

So the UX should be split like this:

### Deterministic UX Layer

Owns:

- start research session
- start literature search
- next paper
- summarize session state
- propose next experiments
- run current design

This layer should not improvise.
It should dispatch to one backend action for each recognized intent.

### Conversational UX Layer

Owns:

- tone
- explanation
- interpretation
- summarization
- clarifying questions when needed
- broader research discussion

This layer can still feel agentic without being responsible for the brittle part of the workflow.

## Important Current Reality

The current command-mode path is only a partial version of this boundary.

Today, explicit commands such as:

- `!research`
- `!more-papers`
- `!add-paper`
- `!next-paper`

are parsed in the OpenClaw workflow-api plugin:

- `services/openclaw-config/plugins/workflow-api-tool/index.ts`

That parser is deterministic once it runs.

But it is not yet a true pre-router, because the model still has to decide to call:

- `workflow_api_dispatch_latest_user_message`

first.

So the current state is:

- deterministic dispatcher: yes
- true pre-router ahead of the model: no

That distinction matters, because it explains why command-mode is materially better than free chat while still sometimes failing at the OpenClaw seam.

## Why This Still Fits The Vision

This does not destroy the "ask to answer" idea.

It changes it from:

- LLM improvises the whole workflow

to:

- the system recognizes common research actions deterministically
- the backend performs them reliably
- the LLM turns the result into a usable research conversation

That is still a research assistant.
It is just a research assistant built on a reliable control surface.

## Product Rule

If a user request should change persistent state, spend compute, or touch the cluster:

- explicit backend action first

If a user request should interpret, compare, explain, or propose:

- agentic reasoning first

This is the simplest rule that reconciles:

- agents
- skills
- explicit API contracts

## Next-Step Guidance

Near-term product work should optimize for this experience:

1. the user can always start or resume research work without fighting the system
2. the system visibly progresses through literature gathering and review
3. the system stores decisions and ideas in the session
4. the system proposes bounded experiments grounded in literature and prior runs
5. the system can execute those experiments through coarse execution templates like `gpu-experiment`

Anything that does not improve that loop is secondary.

## Practical Conclusion

The next product attack path should be:

- deterministic routing for the first research-loop actions
- one-shot backend actions for those flows
- explicit progress reporting
- OpenClaw as the research conversation shell

Not:

- more prompt complexity
- more workflow-family topic classification
- more agent autonomy in the control path
