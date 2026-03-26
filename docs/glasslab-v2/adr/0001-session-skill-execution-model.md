# ADR 0001: Session, Skill, and Execution Template Model

## Status

Accepted

## Context

Glasslab started with workflow families as the main product object because the first useful paths were execution-heavy. That model worked while the system mainly launched bounded jobs.

The product has since shifted toward iterative research work:

- the human works in a research session
- papers are harvested into a queue
- source documents are stored and revisited
- interpretation, assessment, and design happen over the same session state
- workflow family choice comes later, when the work is ready to execute

Keeping workflow families as the top-level ontology makes the system feel backward. It also makes the operator surface too eager to jump to execution before the research state is ready.

## Decision

Glasslab v2 will model the system in three layers:

1. `research sessions`
2. `skills`
3. `execution templates`

Sessions are the primary user-facing object. They hold the problem, queue, source documents, interpretations, assessments, design drafts, and runs.

Skills are bounded backend capabilities that mutate session state in controlled steps. Examples include:

- research problem staging
- literature harvest
- paper intake
- interpretation
- assessment
- design drafting

Execution templates are the later-stage run shapes. Workflow families belong here. They describe how a bounded experiment is launched, not what the whole research workflow is.

## Consequences

- OpenClaw should talk in terms of sessions first, then skills, then execution templates.
- `latest` routes may remain as compatibility aliases, but they are not the preferred primary contract.
- The repo should prefer session-scoped and ID-scoped routes for mutating actions.
- New workflow families should be treated as execution templates, not as the main product taxonomy.
- Future docs and issues should use the session/skill/template vocabulary consistently.

## Related Docs

- `../README.md`
- `../repo-review-2026-03-26.md`
- `../stage-agent-pipeline.md`
- `../research-pipeline-target.md`
