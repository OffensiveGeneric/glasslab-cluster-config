# Next No-Arg Operator Actions

This note answers a practical question:

If Glasslab keeps the production operator path mostly no-arg for now, what are the next few actions worth adding?

The test is simple:

- does the action reduce friction from paper or idea to bounded validation experiment?
- can the backend keep the action deterministic and policy-constrained?
- does the tool avoid asking the model to synthesize brittle structured arguments?

## The Next Four Actions

### 1. `workflow_api_start_paper_intake`

Purpose:

- create one bounded intake record for a paper, note set, or research goal

Why it is worth adding:

- it gives the operator a single stable "start here" action
- it moves the first parsing and normalization step into tracked backend state
- it reduces the need for the operator to remember the next manual step

What should remain backend-owned:

- intake record schema
- required fields
- stored source references
- initial status value

What the model should do:

- decide that the user is asking to begin a paper-to-experiment flow
- summarize the intake confirmation

### 2. `workflow_api_get_last_intake`

Purpose:

- fetch the most recent intake record created by the operator path

Why it is worth adding:

- it gives OpenClaw a stable way to recover context without pretending it remembers everything
- it mirrors the already-working create/get validation-run pattern

What should remain backend-owned:

- intake record ID
- canonical stored source summary
- lifecycle status

What the model should do:

- present the intake cleanly to the operator
- identify what is still missing before design or execution

### 3. `workflow_api_create_design_draft`

Purpose:

- convert the last intake record into a bounded design draft using approved workflow families

Why it is worth adding:

- it is the real bridge from "paper" to "candidate validation experiment"
- it keeps the workflow-family mapping explicit and reviewable
- it lets the backend own the canonical draft schema

What should remain backend-owned:

- approved workflow family selection rules
- allowed dataset and model placeholders
- resource-profile defaults
- artifact expectations

What the model should do:

- trigger the action when the intake is ready
- explain the resulting draft in plain language

### 4. `workflow_api_create_validation_run_from_last_design`

Purpose:

- submit a bounded validation run using the stored design draft instead of a hardcoded demo payload

Why it is worth adding:

- it moves the current fixed validation-run path one step closer to the real research workflow
- it keeps execution repo-managed and deterministic
- it preserves the proven create/get no-arg pattern

What should remain backend-owned:

- manifest derivation
- approval checks
- resource-profile validation
- job submission contract

What the model should do:

- present acceptance or rejection
- explain what was launched

## Why These Four

These four actions create a simple no-arg ladder:

1. start intake
2. inspect intake
3. create design draft
4. create validation run from the stored design

That is enough to test the intended product shape without requiring argumented tool reliability.

## What Not To Add Yet

Do not add no-arg tools just to simulate autonomy.

Avoid things like:

- many one-off lookup tools with overlapping meanings
- direct infrastructure mutation tools
- generic "do research" tools with vague backend behavior
- no-arg tools whose real payload is still mostly hidden prompt logic

## Hardware Reality Check For Better Local Models

Current practical GPU picture:

- `node02`: RTX A4000
- `node01`: Quadro P4000
- `node04`: GTX 1060 6GB

The likely best inference node remains `node02`.

What is realistic with the current hardware:

- trying a better tool-use-capable model in roughly the same size class
- trying a modestly larger quantized model on `node02`
- reducing context length to make room for a somewhat stronger model
- tuning the runtime and parser while keeping the harness unchanged

What is probably not realistic as a boring production path:

- very large local models
- assuming multi-GPU tensor parallel across these mixed cards will be simple
- expecting current hardware to jump straight to a model class that makes structured tool use "solved"

Practical expectation:

- yes, current hardware may support a moderate improvement over the current 4B path
- no, current hardware is unlikely to support a dramatic jump to a much stronger local model tier without meaningful tradeoffs

## Recommended Next Step

Build the next no-arg operator actions first.

In parallel, keep the model experiments modest and measurable:

- try one stronger local candidate on `node02`
- keep the same tool-calling harness
- compare reliability before changing the operator contract

That keeps Glasslab moving toward the real goal even if argumented tools remain unreliable for a while.
