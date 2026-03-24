# Glasslab v2

Glasslab v2 turns the current Titanic-specific path into an explicit, registry-driven workflow platform.

Current live validation reference:

- `../live-state-2026-03-23.md`

Start here:
- `overview.md`: repo-level architecture and control flow
- `workflow-registry.md`: approved workflow family format
- `services.md`: canonical run and artifact contract
- `research-pipeline-target.md`: the intended end-state product shape for Glasslab research workflows
- `no-arg-vs-argumented-tools.md`: why the current safe operator path is mostly no-arg tools, what argumented tools would need to prove, and the current safety rules for repo-managed intake templates
- `next-no-arg-operator-actions.md`: the next operator actions worth adding while the safe path remains mostly no-arg
- `bounded-agent-architecture.md`: how to move toward multi-agent workflows without depending on broad live tool orchestration
- `stage-agent-pipeline.md`: specialized backend agent roles, handoffs, and why OpenClaw should stay at the edge
- `doc-audit-2026-03-24.md`: which v2 docs are still canonical, which are historical scaffolding, and which map to tracker work
- `intake-design-run-implementation-plan.md`: first concrete backend plan for intake -> design draft -> validation run
- `model-improvement-options.md`: stronger model vs ranker vs control-surface vs backend decomposition
- `qwen-fit-for-stage-agents.md`: where the current local Qwen path is useful for backend agents and where it is not
- `cluster-primitives-gap-audit.md`: missing infrastructure primitives and next actions
- `storage-and-state.md`: storage posture and persistence expectations
- `storage-options.md`: where XFS, ZFS, and NFS fit in the stack
- `network-storage-integration.md`: how shared network storage could fit the current live services
- `storage-capacity-inventory-2026-03-23.md`: observed NFS and local-node storage capacity snapshot
- `node-loss-tolerance-options.md`: realistic paths from restart durability toward node-loss tolerance
- `node-loss-tolerance-next-steps.md`: concrete near-term path for backup/restore and OpenClaw relocation work
- `internal-service-exposure.md`: internal-only service access model
- `image-distribution.md`: current image import path and registry migration plan
- `secrets-and-dr.md`: local secret handling and disaster recovery notes
- `runbooks/`: operational steps once manifests and services land
