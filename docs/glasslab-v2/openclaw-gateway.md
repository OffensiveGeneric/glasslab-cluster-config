# OpenClaw Gateway

OpenClaw is the operator shell for Glasslab v2, not the experiment brain.

## Why it sits in front

- It keeps human-facing sessions and routing separate from backend execution.
- It can route literature work, workflow submission, and reporting without embedding infrastructure logic in prompts.
- It allows policy and tool restrictions to live in tracked config instead of hidden runtime state.

## Agent separation

- `operator`: receives user goals and routes them to approved backend paths
- `literature`: extracts structured method details from papers and notes
- `designer`: maps structured requests to approved workflow families
- `reporter`: summarizes artifacts and evaluator output for humans

## Default disabled tools

The default policy should deny:

- arbitrary shell execution
- mutating `kubectl` commands
- filesystem writes outside the approved workspace/config path
- arbitrary outbound HTTP requests
- Git push or repo mutation outside reviewed workflow paths

OpenClaw should only submit approved internal API calls and only after the request has been mapped to a declared workflow family or reporting path.
