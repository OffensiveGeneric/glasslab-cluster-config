# Node02 Interpretation-Agent Experiment

This note turns the current 2026-03-24 live state into a concrete next experiment.

## Live Findings

Validated from `.44` on `2026-03-24`:

- OpenClaw is live again and pointed at `192.168.1.23` with model `deepseek-r1:32b`
- direct chat against the Mac-backed endpoint works
- the current OpenClaw tool-calling harness does **not** work on that backend
- the failure is immediate and explicit:
  - `400 registry.ollama.ai/library/deepseek-r1:32b does not support tools`
- the old in-cluster `vllm` pod is still running on `node02`
- `node02` still has:
  - `nvidia.com/gpu=1`
  - `8` CPU
  - about `64 GiB` memory
- `nvidia-smi` on `node02` showed the current `vllm` process holding about `14.9 GiB` of GPU memory while GPU utilization was `0%`

## Practical Meaning

The Mac-backed path is useful for stronger plain inference right now.

It is **not** currently the right place to push the next automation experiment because the current Ollama-served `deepseek-r1:32b` path is not exposing tool support for OpenClaw.

So the next experiment should move in the other direction:

- keep OpenClaw narrow
- keep the stronger Mac model for chat, interpretation, and future direct backend use
- use cluster-side capacity for the first bounded backend stage agent

## Why Node02 Is The Best First Cluster-Side Target

`node02` is still the most practical first place for a backend stage-agent experiment because:

- it already has the GPU runtime prepared
- it has enough memory for a moderate local inference path
- it is already where the older `vllm` path lived
- repurposing it is smaller than inventing a new serving lane from scratch

The one required step first is:

- retire or replace the old `glasslab-agents/vllm` pod that is still reserving the GPU

## Best First Agent: Interpretation

The best first backend agent experiment is the **paper interpretation** stage.

Why this is the best fit:

- the task is useful and fuzzy enough to benefit from a model
- it is not the final execution authority
- the output already has an explicit backend schema
- failure can stop at review without risking run creation

Existing backend support already present in `workflow-api`:

- `POST /interpretations/from-latest-intake`
- `GET /interpretations/latest`
- `POST /replicability-assessments/from-latest-interpretation`
- `GET /replicability-assessments/latest`

Current code already has:

- `InterpretationRecord`
- `ReplicabilityAssessmentRecord`
- deterministic fallback builders in `workflow-api`

That means the first agent does not need to invent a whole new product boundary.

## Recommended Experiment Shape

Use `node02` for a bounded internal service that does one job:

- consume an intake-like record
- return an interpretation draft

Suggested internal API:

- `POST /interpret-intake`

Input:

- latest intake record or an explicit intake payload

Output:

- `InterpretationRecord`-shaped draft fields:
  - `extracted_method_summary`
  - `candidate_workflow_families`
  - `dataset_hints`
  - `evaluation_targets`
  - `extracted_claims`
  - `unresolved_questions`

`workflow-api` should remain the owner of:

- fetching the intake record
- validating the returned shape
- persisting the final interpretation record
- deciding whether to fall back to deterministic interpretation
- creating any later replicability assessment or design draft

## What Not To Do First

Do not first use `node02` for:

- OpenClaw operator tool-calling experiments
- final approval decisions
- canonical run manifest generation
- infrastructure mutation
- broad multi-stage orchestration in one model loop

The point of the experiment is to validate one bounded backend stage, not to recreate the old "general agent" trap.

## Near-Term Sequence

1. scale down or replace the old `vllm` Deployment on `node02`
2. stand up one bounded interpretation service on `node02`
3. have `workflow-api` call it optionally behind a feature flag or explicit mode
4. store the returned interpretation only after schema and policy validation
5. compare:
   - deterministic-only interpretation
   - model-assisted interpretation on `node02`
6. widen only if interpretation quality is materially better

## Current Conclusion

The first realistic "agent that does part of the research process" is no longer "make OpenClaw itself more agentic."

It is:

- keep OpenClaw as the narrow front door
- keep the Mac as stronger primary chat inference
- use `node02` for a bounded interpretation-stage backend agent experiment
