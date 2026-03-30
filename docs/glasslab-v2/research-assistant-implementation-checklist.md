# Research Assistant Implementation Checklist

This checklist turns [research-assistant-infra-proposal.md](./research-assistant-infra-proposal.md) into a concrete execution order.

The priority is not "more agents."
The priority is a usable research loop with deterministic control where it matters.

## Phase 1: Deterministic Front Door

- add a deterministic intent router for:
  - start research session
  - start literature search
  - next paper
  - summarize current literature
  - propose next experiments
  - run current design
- keep OpenClaw as the conversational shell behind that router
- stop requiring OpenClaw to decide whether those intents should touch the backend
- keep a fallback path for non-matching conversational turns

Success condition:

- a plain-language "start a literature search on X" request always produces one backend action without relying on LLM tool choice

## Phase 2: One-Shot Research Actions

- keep `POST /research-sessions/start-literature-search`
- add:
  - `POST /research-sessions/advance-literature-review`
  - `POST /research-sessions/stage-next-paper`
  - `POST /research-sessions/summarize-literature`
  - `POST /research-sessions/propose-next-experiments`
  - `POST /research-sessions/prepare-current-design`
  - `POST /research-sessions/run-current-design`
- make each action own orchestration internally instead of exposing multi-step chat sequencing
- ensure each action persists one `OperationRecord`

Success condition:

- the user-facing research loop is driven by a small set of backend-owned actions instead of OpenClaw chaining tools

## Phase 2.5: Topic-Agnostic Literature Backbone

- widen literature discovery across:
  - metadata backbones like OpenAlex / Crossref / PubMed / DBLP / DataCite
  - open-access full-text sources like arXiv / PMC / repositories
  - discipline-specific indexes where needed
  - grey literature where it improves breadth
- normalize identifiers before fetch:
  - DOI
  - PMID / PMCID
  - arXiv ID
  - title hash fallback
- use a session-aware paper ranker to choose which candidates enter the queue
- keep institutional library access as an access-resolution layer, not the first corpus

Success condition:

- a new research session can discover, rank, fetch, and digest papers for arbitrary topics instead of depending on a narrow seed corpus

## Phase 3: Explicit Progress And Activity Feed

- add a durable session activity feed
- connect it to `OperationRecord` lifecycle
- emit explicit statuses for:
  - queued
  - running
  - waiting-on-fetch
  - papers-found
  - paper-ingested
  - interpretation-ready
  - design-ready
  - run-submitted
  - run-complete
  - comparison-ready
- expose one session-status read optimized for chat reporting

Success condition:

- the system can say what it is doing without pretending a slow turn is an API outage

## Phase 4: Background Workers For Slow Steps

- move literature harvest off the request path
- move source-document fetch and PDF/text extraction off the request path
- move interpretation generation off the request path
- move evaluation/report generation off the request path
- use bounded workers and durable operation state
- use NATS only where it buys durable decoupling instead of adding complexity for its own sake

Success condition:

- the user sees "started" and "in progress" states quickly, and slow work finishes through workers instead of long chat hangs

## Phase 5: Session Memory As The Research Workspace

- keep session notes durable
- keep decision log durable
- keep next experiment ideas durable
- add explicit literature-summary records
- add explicit experiment-comparison records
- ensure new run results are written back into the session

Success condition:

- the research assistant can continue a conversation across days without reconstructing the whole context from chat

## Phase 6: GPU Experiment Lane

- keep the execution family coarse as `gpu-experiment`
- maintain at least one real GPU runner image for:
  - `torch`
  - `torchvision`
  - common CV workflows
- make preflight report missing runtime capabilities clearly
- validate dataset and artifact paths for GPU runs
- record GPU run artifacts back into the session

Success condition:

- a session can move from CV/ML literature to one bounded GPU experiment without inventing a new workflow family

## Phase 7: Stronger Research Assistance

- improve interpretation quality
- improve next-experiment proposal quality
- compare runs explicitly inside the session
- optionally evaluate a stronger model for:
  - literature synthesis
  - experiment proposal
  - conversational quality
- do not reintroduce model-owned orchestration for the critical control path

Success condition:

- the system can suggest bounded experiment deltas grounded in literature and prior runs

## Explicit De-Priorities

These are not the near-term milestone:

- a large stable of stage-specific "agents" as the primary product concept
- topic-specific workflow families
- OpenClaw as the planner for multi-step workflow control
- prompt-only fixes for orchestration failures

## Issue Mapping

- `#60`: deterministic intent router
- `#62`: general literature ingestion, ranking, and digest breadth
- `#56`: demote mutating `latest` aliases and keep session-scoped contracts primary
- `#51`: sessions / skills / execution-templates framing
- `#49`: `gpu-experiment` as the main GPU/CV execution shape
- `#58`: provenance and live-state visibility
- `#57`: repo/live-state documentation and operational clarity
- `#55`: durable schedule and execution audit path
