# Node02 Role Decision

This note narrows issue `#36`.

`node02` cannot stay in an ambiguous state forever.

Right now it is simultaneously:

- the old in-cluster `vllm` host
- a still-reserved GPU lane
- the best candidate for the first cluster-side bounded agent experiment

Those roles conflict.

## Current Choices

There are only three realistic roles for `node02`.

### 1. Keep Legacy vLLM As Active Fallback

Meaning:

- continue running `glasslab-agents/vllm`
- preserve the old cluster-local tool-capable path as a standby lane

Pros:

- preserves a known older local tool-calling path
- gives OpenClaw a cluster-local fallback if the Mac path regresses

Cons:

- keeps the only GPU on `node02` occupied
- delays cluster-side bounded-agent experiments
- keeps the architecture in a mixed half-migrated state

### 2. Retire Legacy vLLM And Reclaim Node02

Meaning:

- scale down or remove the old `vllm` deployment
- treat `node02` GPU capacity as available for the next bounded backend-agent experiment

Pros:

- frees the GPU for new work
- reduces architectural confusion
- aligns with the current Mac-first inference direction

Cons:

- removes the easiest local fallback if Mac-backed inference has problems
- requires confidence that the old lane is no longer operationally necessary

### 3. Replace Legacy vLLM With A New Explicit Cluster Role

Meaning:

- shut down the old `vllm` deployment
- immediately repurpose `node02` for a different bounded service
- most likely:
  - interpretation-agent backend experiment
  - or a future dedicated in-cluster serving lane with a clearly reviewed purpose

Pros:

- turns reclaimed capacity into something useful immediately
- avoids the false comfort of keeping the old deployment around forever

Cons:

- requires a more explicit rollout decision instead of just "leave it there for now"

## Recommendation

The recommended sequence is:

1. treat the Mac path as the primary chat/inference lane
2. keep `.12` as the ranker / secondary model lane
3. retire the old `node02` `vllm` deployment once the Mac-backed operator path is judged operationally acceptable
4. repurpose `node02` for the first bounded cluster-side backend-agent experiment

That means option 3 is the intended end state, not option 1.

## Practical Retirement Gate

Do not retire the old `vllm` lane merely because the docs say it is obsolete.

Retire it when these are true:

- Mac-backed OpenClaw path is stable enough for the current operator workload
- `.12` remains available as the first native-Ollama tool-capable fallback candidate
- the next bounded-agent experiment is ready enough to justify reclaiming node02 capacity

## Recommended First Reuse

The first reuse should still be the bounded interpretation-stage experiment, because:

- the output already has a schema in `workflow-api`
- failure can stop safely at review
- it uses reclaimed capacity for backend value instead of just swapping one serving stack for another

## What To Avoid

Avoid letting `node02` become:

- a vague "maybe fallback someday" box
- a permanent zombie `vllm` reservation
- a second ad hoc general-purpose inference host without a clear owner

## Bottom Line

The repo direction should be:

- Mac-backed primary inference
- Mac-backed secondary/ranker support
- `node02` reclaimed for bounded cluster-side backend work

The old `vllm` lane should be kept only until that transition is explicitly judged safe, not as the long-term default.

## References

- `node02-interpretation-agent-experiment.md`
- `../machine-state-2026-03-24.md`
- `resume-next-session-2026-03-24.md`
