# Grossberg KB Notes For Runner

These notes are a useful reference, but only part of them should shape Glasslab right now.

## What To Borrow Now

- Strong PDF and webpage ingestion.
  We should keep improving direct source ingestion because the runner needs clean source context without depending on the old literature queue.

- Structured extraction before LLM interpretation.
  The right pattern is still:
  source document -> extracted text and metadata -> bounded interpretation -> `MethodSpec` -> run.

- Academic metadata discipline.
  Stable paper/source metadata, citations, and project-local source tracking are useful because they make sessions auditable and make future trend tracking easier.

- NotebookLM-style knowledge as an upstream authoring aid.
  NotebookLM-style synthesis is useful for generating technique knowledge and structured cards, but Glasslab should consume validated structured results rather than raw long-form prose.

- Per-project organization.
  A project should naturally accumulate:
  raw sources, extracted markdown/text, structured notes, run outputs, and comparison outputs.
  That matches the direction of session-owned source documents plus bounded experiment state.

## What To Defer

- A giant LLM-maintained wiki as the primary product.
  That is interesting, but it is not the bottleneck for making Glasslab useful right now.

- Full NotebookLM replacement.
  We do not need a general-purpose knowledge base product before the runner can execute and compare real experiments.

- Fancy multi-tool agent navigation over a huge markdown corpus.
  This is a later optimization, not part of the shortest path to useful experiments.

- Audio/podcast and dynamic dashboard output modes.
  Nice future affordances, but not core to the current experiment-runner objective.

- Heavy emphasis on general literature trend tracking.
  We can add this later, but the current runner-first priority is manual source add plus bounded execution.

## What This Means For Glasslab

The useful subset of the Grossberg material is:

- better source ingestion
- better source extraction
- better structured technique knowledge
- better provenance
- better question-answering over attached source documents when needed

The product focus should remain:

- bounded experiment creation
- parallel method comparison
- unattended iteration inside approved limits
- clearer session and campaign state

So the right interpretation of these notes is:

- use them to improve the input knowledge layer
- do not let them pull Glasslab back into a broad “research wiki product” detour

## Immediate Practical Use

These references should inform:

- future `!add-pdf` and `!add-url` extraction improvements
- source-to-markdown normalization
- technique-card authoring and import
- session-bound source-document Q&A

They should not reset the current priority away from the experiment runner.
