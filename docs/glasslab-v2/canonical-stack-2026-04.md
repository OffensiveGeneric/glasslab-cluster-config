# Canonical Stack 2026-04

This note is the short answer to a recurring repo problem: the system does not
need less architecture. It needs fewer competing architectures.

## Primary

- one control plane:
  - `workflow-api`
- one deterministic operator command path:
  - `whatsapp-gateway -> research-ingress -> research-command-router -> workflow-api`
- one metadata store:
  - `Postgres`
- one artifact/file plane:
  - `NFS` and `MinIO`
- one image distribution path:
  - `GHCR`
- one bounded model-serving lane for the stage agents:
  - exo OpenAI-compatible endpoint on `.21`
- one admin/apply host for live validation:
  - `.44`

## Secondary

- `OpenClaw`
  - optional conversational surface
  - not part of the deterministic command path
  - should not be treated as a co-equal orchestrator for `!start`, `!status`,
    `!run`, `!next`, or `!compare`

## Legacy / Reference

- manual `ctr import` image distribution
  - break-glass only
- JSON-on-artifacts-share as a long-term metadata system of record
  - convenient during bootstrap
  - not the target end state
- older Ollama-specific bounded agent paths
  - superseded by the exo-backed bounded inference lane

## Practical simplification rules

1. Backend-owned command turns stay deterministic.
   - `!start`, `!status`, `!run`, `!next`, and `!compare` should execute through
     the repo-owned command path with no OpenClaw dependency on the command turn.

2. Postgres owns records; file stores own files.
   - session and stage metadata should converge toward `Postgres`
   - `NFS` and `MinIO` should carry blobs, artifacts, reports, and source
     documents

3. Keep internal services private.
   - `workflow-api`, `Postgres`, `NATS`, and `MinIO` stay `ClusterIP`
   - expose only genuinely human-facing surfaces

4. Treat `.44` as four separate responsibilities, not one embarrassment.
   - admin workstation
   - runtime export/apply host
   - secret source of truth
   - image fallback

5. Do not add async/event machinery just to make the stack look modern.
   - `NATS` should be used where durable decoupling buys something concrete
   - not as architecture cosplay

## Bounded agent inference stance

The bounded `intake`, `interpretation`, `design`, and `assessment` lanes should
share one coherent backend story.

Current canonical choice:

- provider type:
  - `openai-compatible`
- serving endpoint:
  - exo on `.21`
- default model:
  - `mlx-community/Qwen3-Coder-Next-4bit`

This keeps the deterministic WhatsApp command path separate from the model lane
while reducing the number of inference stacks the repo has to reason about.
