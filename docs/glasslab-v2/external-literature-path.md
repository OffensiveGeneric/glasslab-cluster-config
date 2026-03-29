# External Literature Path

## Goal

Move Glasslab from a seed-manifest-only paper picker to a real literature pipeline
 that can:

- search relevant sources for a research session topic
- compare candidate papers and methodologies
- fetch source documents through lawful access paths
- attach fetched documents to the session
- preserve the current seed manifest as a bounded fallback

This is the correct next step once the session/command front door is usable enough
to trigger backend actions reliably.

## Current State

Right now, literature harvest is not a broad search.

`workflow-api` calls `intake-agent`'s problem-harvester plan endpoint, which selects
 from a repo-managed seed manifest:

- [glasslab_paper_harvester_seed_manifest.yaml](/home/gr66ss/cluster-config/services/intake-agent/seeds/glasslab_paper_harvester_seed_manifest.yaml)

That means:

- candidate papers come from a bounded YAML shortlist
- ranking is lexical overlap plus a few static heuristics
- weak topic overlap falls back to a small approved corpus

This is useful as a deterministic bootstrap path, but it is not a real literature assistant.

## Desired Architecture

The external literature path should be backend-owned and session-centered.

Flow:

1. research session topic exists
2. backend search layer queries external literature providers
3. backend ranks candidate papers for the session
4. backend resolves lawful fetch URLs
5. backend ingests fetched source documents
6. backend attaches results to session state
7. OpenClaw summarizes and helps compare the findings

OpenClaw should not browse the web itself for this. The search and fetch path should
 live in backend services.

## Search Sources

Preferred first sources:

- OpenAlex
- Crossref
- arXiv
- Semantic Scholar

Why:

- broad metadata coverage
- stable APIs
- citation and venue metadata
- strong open-access detection potential

Initial rule:

- search metadata first
- fetch documents second

Do not start with scraping PDFs blindly.

## Fetch Policy

Allowed fetch priority:

1. arXiv PDF / abstract page
2. publisher or venue page with public PDF
3. official conference proceedings page
4. institutional-access publisher URL

The system should not use Sci-Hub or similar unauthorized sources.

Instead, lawful fetch support should be:

- open-access URL resolution
- official publisher page fetch
- institutional-access URL pass-through for user- or environment-backed access

## Session Integration

The external literature path should produce backend records, not just chat text.

Per session, store:

- search query set
- search provider hits
- ranked candidate list
- fetch attempts
- fetch status per paper
- source document records
- provenance for where each document came from

That means the session can later answer:

- what was searched
- what was found
- what was fetched
- what failed and why
- which papers are still just metadata candidates

## Relationship To Seed Corpus

Keep the seed manifest.

Role of the seed manifest after external search exists:

- deterministic bootstrap corpus
- bounded fallback when external search is unavailable
- approved reference set for internal validation and demos

The seed manifest should stop pretending to be the full literature path.

## Suggested Service Boundary

Add a bounded backend component for external literature work.

Possible shape:

- `literature-search` capability inside `workflow-api`
- or a small dedicated `literature-agent` / `literature-service` behind `workflow-api`

Recommended first contract:

- `POST /research-sessions/{session_id}/skills/external-literature-search`
- `GET /research-sessions/{session_id}/literature-candidates`
- `POST /research-sessions/{session_id}/literature-candidates/{candidate_id}/fetch`

That keeps:

- search
- ranking
- fetch

explicit and durable.

## Ranking

Do not rely on simple lexical overlap alone once external sources exist.

First pass ranking inputs:

- title/abstract overlap with research problem
- venue signal
- recency
- open-access availability
- methodological fit
- benchmark/dataset overlap
- code/artifact availability

Keep the result transparent:

- score
- reasons
- fetchability

This is important so the user can inspect why the system picked a paper.

## First PR Sequence

### PR 1

Add external literature metadata search without document fetch.

Deliverables:

- provider client module
- session-scoped search endpoint
- candidate record schema
- persistence for candidate lists and provenance

### PR 2

Add lawful fetch resolution and source-document ingestion.

Deliverables:

- fetch resolver
- open-access-first fetch logic
- source document creation from fetched candidate
- operation records for fetch attempts

### PR 3

Blend external results with seed-manifest fallback.

Deliverables:

- prefer external search when available
- fallback to seed manifest when search fails or returns weak coverage
- expose coverage mode in session context

### PR 4

Expose comparison helpers.

Deliverables:

- compare candidate methodologies
- compare datasets / benchmarks mentioned across papers
- session-level literature summary over fetched docs

## User-Facing Goal

The user should eventually be able to say:

- `!research forged art detection with computer vision methods and open datasets`

and get:

- a real literature search over external sources
- a lawful fetch pipeline
- actual session-attached papers to compare
- a summary of methodologies worth investigating

That is the right path to making Glasslab behave like a real research assistant,
 rather than a seed-corpus demo.
