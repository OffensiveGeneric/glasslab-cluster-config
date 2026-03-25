# Tool Choice Patch Experiment

This note turns issue `#11` into a bounded experiment instead of a standing architectural wish.

The repo already established the important negative result:

- the reachable OpenClaw operator path does not currently expose `tool_choice`
- this is true not only for `openclaw agent`, but also for the reachable gateway RPC schemas

That means the next realistic question is not "can prompts solve this?"

It is:

- is Glasslab willing to carry a small OpenClaw patch for experimental pinned-tool use?

## Scope

This experiment is intentionally narrow.

It is only for:

- controlled tool-selection experiments
- read-only or otherwise bounded tool surfaces
- measuring whether pinned tool choice improves reliability for tiny argumented tools

It is not for:

- widening the production operator surface
- making OpenClaw more autonomous
- bypassing backend approval boundaries

## Minimal Desired Capability

One reachable request path should accept:

- `tool_choice: "required"`

and ideally also:

- `tool_choice: { "type": "function", "function": { "name": "<tool-name>" } }`

That is enough to separate:

- tool-selection ambiguity

from:

- argument-generation quality

## Recommended Experiment Boundary

If Glasslab carries a patch, keep it behind an explicit experimental lane:

- separate runtime or separate agent
- read-only tools only
- no state-changing workflow submission in the first pass
- no production dependency on the patched path

## Proposed Validation Sequence

1. expose `tool_choice` on one reachable request schema
2. keep the current no-arg production path unchanged
3. add one experimental read-only agent or route
4. rerun `./scripts/check-openclaw-tool-calling.sh --attempts 5`
5. compare:
   - auto tool choice
   - `required`
   - pinned function name

## Success Criteria

The patch is only worth keeping if it produces a materially clearer answer.

Good outcomes:

- tiny argumented tool succeeds reliably when pinned
- no-arg baseline remains unchanged
- the patch surface stays narrow and maintainable

Bad outcomes:

- pinned tool choice still produces empty or invalid args
- the patch requires broad divergence from upstream OpenClaw
- the experiment starts leaking into the production operator path

## Decision Rule

If pinned tool choice still does not make tiny argumented tools reliable, Glasslab should stop spending time here and keep investing in:

- backend stage agents
- repo-managed no-arg wrappers
- stronger model/runtime paths

If pinned tool choice does help, then the question becomes whether the patch is small enough to carry for ongoing experimental use.

## Recommendation

Treat `tool_choice` as an experimental capability branch.

Do not treat it as a prerequisite for the main Glasslab architecture.

## References

- `tool-choice-exposure-options.md`
- `tool-calling-reliability.md`
- `stage-agent-pipeline.md`
