# Workflow Registry

This directory holds explicit workflow family definitions reviewed into Git. `workflow-api` should only accept runs that match entries declared here.

Read this directory as committed contract, not as proof that every declared template is live-runnable right now.

Important boundary:

- these entries are now best understood as execution templates
- they are not the primary conversational/product ontology anymore
- research sessions and stage state sit above them

Each registry entry should say, machine-readably:

- whether the family is actually executable right now
- which submission backend it expects
- what blockers still keep it in a declared-only state

That means definitions should keep these fields honest:

- `execution_status`
- `submission_backend`
- `execution_blockers`

If a family is declared in Git but not actually runnable through `workflow-api`,
it should be marked that way here instead of letting preflight or operator UX
imply more than the backend can really do.

Current approved templates include CPU tabular, literature-to-experiment, a
declared-only replication lane, and a coarse `gpu-experiment` template that
requests `nvidia.com/gpu` on GPU-candidate nodes. These should be read as
execution shapes the cluster can run, not as a taxonomy of research topics.

What is committed here:

- execution-template definitions
- expected artifact contracts
- resource profiles
- execution readiness metadata

What must still be checked elsewhere:

- whether the current live cluster actually satisfies the template preflight
- whether the referenced runner image is available and healthy
- whether the current deployment of `workflow-api` actually exposes the intended behavior
