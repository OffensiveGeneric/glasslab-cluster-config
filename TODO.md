# Glasslab Work Queue

Last reviewed: 2026-08-06

GitHub Issues are the authoritative backlog. This file is a compact priority
index for humans and coding agents arriving in the repository; it must not
duplicate complete task specifications or maintain an independent status.

Current issues:

- [all open work](https://github.com/ccny-glasslab/glasslab-cluster-config/issues)
- [ready work](https://github.com/ccny-glasslab/glasslab-cluster-config/issues?q=is%3Aissue%20state%3Aopen%20label%3Astate%3Aready)
- [newcomer work](https://github.com/ccny-glasslab/glasslab-cluster-config/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22)

## P0: Restore The End-To-End Research Loop

- [#104 Prevent missing Honeydew contract metadata from failing a run](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/104)
- [#92 Add terminal research-run checkpoint retry](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/92)
- [#100 Complete corrected Wine clustering run](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/100), blocked by #92

## P1: Make Operation Observable And Faster

- [#95 Expose structured research-run turn inspection](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/95)
- [#94 Add Discord research run status and discovery commands](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/94)
- [#93 Compact research-agent evidence prompts](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/93)
- [#99 Add research runtime storage retention and cache cleanup](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/99)

## P1: Validate General Research Tasks

- [#98 Validate an arbitrary-dataset research workflow end to end](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/98)
- [#101 Complete Fashion-MNIST compatibility run](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/101)
- [#96 Evaluate Hermes as a research-agent runtime adapter](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/96)

## P2: Durability And Maintenance

- [#97 Plan PostgreSQL migration for the research orchestrator](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/97)
- [#102 Consolidate current docs and triage legacy issues](https://github.com/ccny-glasslab/glasslab-cluster-config/issues/102)

## Maintenance Rule

When work is discovered, create or update a GitHub issue before changing this
index. The issue must contain scope, acceptance criteria, relevant area and
priority labels, dependencies, and enough context for a new contributor to
start without reconstructing chat history.

When work starts, comment with the intended approach and link the branch or
pull request. Pull requests should use `Closes #<issue>` when they fully satisfy
the issue. Close abandoned work with a reason rather than deleting it. Update
this file only when the short prioritized index changes.

Completed work belongs in release notes, design docs, or the issue history,
not in a growing completed-items section here.
