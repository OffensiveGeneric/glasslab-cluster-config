# External Literature Path

Status: aspirational / secondary.

This file describes a future external-literature capability. It is not the
current product center. Current product docs should frame literature as bounded
source intake and review, not as the primary identity of the system.

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

## Source Coverage

The broadest reasonable literature path should cover multiple source classes.

### Core Metadata And Identifier Sources

These should be the backbone for discovery, deduping, and entity resolution.

- OpenAlex
- Crossref
- PubMed
- DBLP
- DataCite

Why:

- broad identifier coverage
- strong DOI / author / venue / institution metadata
- better deduping and citation-graph linkage than raw publisher scraping

### Open-Access Full-Text Sources

These are the easiest lawful full-text sources to scale.

- arXiv
- PubMed Central
- bioRxiv / medRxiv
- DOAJ-linked journals
- CORE
- institutional repositories
- Zenodo / OSF and similar repositories

These should be the first-choice fetch layer when full text is available.

### Discipline-Specific Indexes

These should plug into the same connector model, even if they are not all used on day one.

- IEEE Xplore
- ACM Digital Library
- RePEc / SSRN
- ERIC
- PsycINFO
- ADS / MathSciNet / AGRICOLA and similar field-specific indexes where relevant

### Grey Literature

Breadth depends heavily on this class.

- theses and dissertations
- technical reports
- white papers
- government reports
- standards
- patents
- grant reports
- workshop papers and posters

### Library / Discovery Layer

This is where institutional access should live.

- library discovery service
- OpenURL link resolver
- proxied vendor links
- licensed vendor databases exposed through approved APIs

Important boundary:

- use the library layer to resolve access
- do not make it the first bulk-ingestion target

Initial rule:

- discover metadata first
- resolve identifiers second
- prefer open-access fetch third
- consult the library layer only when open access is unavailable

Do not start with scraping PDFs blindly.

## Fetch Policy

Allowed fetch priority:

1. open-access full text from arXiv / PMC / repositories / journal mirrors that permit access
2. publisher or venue page with public PDF
3. official conference proceedings page
4. institutional-access publisher URL resolved through the library layer

The system should not use Sci-Hub or similar unauthorized sources.

Instead, lawful fetch support should be:

- open-access URL resolution
- official publisher page fetch
- institutional-access URL resolution and pass-through for user- or environment-backed access

Safe default storage when license is unclear:

- metadata
- identifiers
- abstract
- citation graph information
- access status
- resolver link

Store extracted full text only when the access path and license clearly permit it.

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
- citation / graph context where available
- novelty / diversity against papers already in the session

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
- multi-source connector model
- session-scoped search endpoint
- candidate record schema
- persistence for candidate lists and provenance

### PR 2

Add lawful fetch resolution and source-document ingestion.

Deliverables:

- fetch resolver
- open-access-first fetch logic
- identifier normalization across DOI / PMID / PMCID / arXiv ID / title hash
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

### PR 5

Integrate institutional library resolution.

Deliverables:

- OpenURL or resolver integration if available
- holdings / access-status lookup
- licensed-access resolver links
- clear separation between discovery, access resolution, and fetch

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
