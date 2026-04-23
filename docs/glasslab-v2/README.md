# Glasslab v2

This directory has accumulated several generations of product and infrastructure
thinking. Not all of it is equally current.

Read it in this order.

## Current Source Of Truth

These files define the current product shape and should be read first:

- `canonical-stack-2026-04.md`
- `command-surface-spec.md`
- `router-and-backend-contract.md`
- `deprecation-map-2026-04.md`
- `product-cleanup-2026-04.md`

Short version:

- Glasslab is runner-first
- the primary control path is repo-owned and deterministic
- `workflow-api` is the control plane
- there is no supported OpenClaw runtime path in the current product
- Postgres should own records
- shared filesystem and/or MinIO should own files

## Current Architecture And Implementation Notes

These remain current and useful after the cleanup pass:

- `overview.md`
- `generic-experiment-contract.md`
- `generic-experiment-implementation-plan.md`
- `artifact-contract.md`
- `storage-contract-2026-04.md`
- `comparison-record-contract.md`
- `near-term-byte-plane-decision.md`
- `stateful-object-inventory-2026-04.md`
- `workflow-registry.md`
- `services.md`
- `research-ingress.md`
- `research-command-router.md`
- `custom-chat-shell-plan.md`
- `bounded-experiment-runner-priority.md`
- `runner-first-technique-knowledge-plan.md`
- `technique-catalog.md`
- `workflow-api-schedules.md`
- `schedule-worker-plan.md`
- `interpretation-agent-service.md`

## Audit And Migration References

These are analysis/reference documents, not current product contracts:

- `artifact-contract-audit-2026-04.md`
- `doc-contradictions-2026-04.md`
- `generic-experiment-gap-audit-2026-04.md`
- `workload-registry-evolution-notes-2026-04.md`
- `reference/glasslab-workload-contract-v0.md`

## Current Operator / Infrastructure References

These are still useful operational documents:

- `state-and-storage-map-2026-03-27.md`
- `cluster-primitives-gap-audit.md`
- `image-distribution.md`
- `internal-service-exposure.md`
- `secrets-and-dr.md`
- `provisioner-dependence-inventory.md`
- `runbooks/`

Important caveat:

- some of these documents describe current technical debt
- they are not endorsements of the target end state

## Current Product Language

Use these concepts in current docs:

- session
- source intake
- plan
- preflight
- run
- compare
- decide
- next bounded variant

Avoid centering current docs on:

- literature pipeline
- OpenClaw operator shell
- general research assistant
- multi-agent orchestration

## Historical / Transitional Material

These documents remain valuable for context, but they are not the current
source of truth:

- March live-state notes
- resume-next-session notes
- old Ollama/OpenClaw path docs
- legacy `vllm` retirement notes
- early research-assistant framing docs

Use:

- `historical/README.md`

to find them intentionally instead of treating them as current defaults.

## Directory Structure

This directory is now organized conceptually as:

- current source-of-truth docs at the top level
- runbooks under `runbooks/`
- supporting references under `references/`
- current and historical indexes under:
  - `current/`
  - `historical/`

The old flat file set still exists for compatibility, but the indexes above are
the intended navigation path.
