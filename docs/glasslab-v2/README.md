# Glasslab v2

Glasslab v2 turns the current Titanic-specific path into an explicit, registry-driven workflow platform.

Current live validation reference:

- `../live-state-2026-03-19.md`

Start here:
- `overview.md`: repo-level architecture and control flow
- `workflow-registry.md`: approved workflow family format
- `services.md`: canonical run and artifact contract
- `research-pipeline-target.md`: the intended end-state product shape for Glasslab research workflows
- `no-arg-vs-argumented-tools.md`: why the current safe operator path is mostly no-arg tools and what argumented tools would need to prove
- `next-no-arg-operator-actions.md`: the next operator actions worth adding while the safe path remains mostly no-arg
- `bounded-agent-architecture.md`: how to move toward multi-agent workflows without depending on broad live tool orchestration
- `intake-design-run-implementation-plan.md`: first concrete backend plan for intake -> design draft -> validation run
- `model-improvement-options.md`: stronger model vs ranker vs control-surface vs backend decomposition
- `cluster-primitives-gap-audit.md`: missing infrastructure primitives and next actions
- `storage-and-state.md`: storage posture and persistence expectations
- `storage-options.md`: where XFS, ZFS, and NFS fit in the stack
- `network-storage-integration.md`: how shared network storage could fit the current live services
- `internal-service-exposure.md`: internal-only service access model
- `image-distribution.md`: current image import path and registry migration plan
- `secrets-and-dr.md`: local secret handling and disaster recovery notes
- `runbooks/`: operational steps once manifests and services land
