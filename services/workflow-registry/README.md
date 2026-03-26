# Workflow Registry

This directory holds explicit workflow family definitions reviewed into Git. `workflow-api` should only accept runs that match entries declared here.

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
