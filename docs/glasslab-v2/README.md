# Glasslab v2

Glasslab v2 turns the current Titanic-specific path into an explicit, registry-driven workflow platform.

Current live validation reference:

- `../live-state-2026-03-23.md`
- `../live-state-2026-03-24.md`
- `../machine-state-2026-03-24.md`

Canonical planning and architecture:
- `overview.md`: repo-level architecture and control flow
- `workflow-registry.md`: approved workflow family format
- `services.md`: canonical run and artifact contract
- `research-pipeline-target.md`: the intended end-state product shape for Glasslab research workflows
- `stage-agent-pipeline.md`: specialized backend agent roles, handoffs, and why OpenClaw should stay at the edge
- `doc-audit-2026-03-24.md`: which v2 docs are still canonical, which are historical scaffolding, and which map to tracker work
- `intake-design-run-implementation-plan.md`: first concrete backend plan for intake -> design draft -> validation run
- `model-improvement-options.md`: stronger model vs ranker vs control-surface vs backend decomposition
- `ranker-service-shape.md`: first concrete API and ownership boundary for a bounded ranker service
- `mac-studio-inference.md`: decision and switch path for using a Mac Studio as the primary external inference host
- `mac-service-host-boundary.md`: why the Macs should stay outside kubeadm and act as service hosts first
- `ollama-native-openclaw.md`: why remote Ollama should use native OpenClaw provider mode instead of `/v1` when tool calling matters
- `node02-interpretation-agent-experiment.md`: why the first cluster-side stage-agent experiment should be a bounded interpretation worker on `node02`
- `interpretation-agent-service.md`: concrete contract and ownership boundary for the first in-cluster stage-agent service
- `stage-agent-api-changes.md`: concrete `workflow-api`, service-contract, and config changes needed for the staged backend-agent path
- `evaluation-boundary.md`: why evaluation should stay deterministic first and where later narrative enrichment could fit
- `run-preparation-boundary.md`: why canonical run preparation should remain inside `workflow-api`
- `execution-boundary.md`: why execution remains deterministic and backend-owned instead of becoming a free-form agent
- `reporting-boundary.md`: why reporting should stay grounded in explicit artifacts and deterministic rendering first
- `resume-next-session-2026-03-24.md`: concise checkpoint for resuming after the `qwen3:30b` pull and Mac-native tool evaluation
- `qwen-fit-for-stage-agents.md`: where the current local Qwen path is useful for backend agents and where it is not
- `approval-tier-unattended-ops-plan.md`: concrete plan for unattended digests and approved reruns behind approval tiers
- `workflow-api-schedules.md`: current stored schedule endpoints for digests and approved reruns
- `schedule-execution-boundaries.md`: fail-closed execution rules for stored schedules and future `run-now` support
- `operator-access-options.md`: narrowed decision between Tailscale or reverse proxy for stable operator-facing access
- `openclaw-runtime-portability.md`: what has and has not been reduced in the `.44`-special OpenClaw runtime path
- `external-researcher-what-we-can-offer-now.md`: practical current answer for what outside researchers can safely use today
- `external-researcher-hardening-gaps.md`: what must be hardened before outside researchers should be treated as first-class cluster users
- `tool-choice-exposure-options.md`: realistic paths for issue `#11` and why runtime YAML alone is not enough
- `provisioner-dependence-inventory.md`: splits the remaining `.44` dependence into image, runtime, secret, and admin-context buckets

Still-current supporting design notes:
- `no-arg-vs-argumented-tools.md`: why the current safe operator path is mostly no-arg tools, what argumented tools would need to prove, and the current safety rules for repo-managed intake templates
- `bounded-agent-architecture.md`: earlier backend-agent framing that now points toward `stage-agent-pipeline.md`
- `next-no-arg-operator-actions.md`: original no-arg action ladder that is now partly implemented and mainly useful as historical context

Operational and infrastructure references:
- `cluster-primitives-gap-audit.md`: missing infrastructure primitives and next actions
- `storage-and-state.md`: storage posture and persistence expectations
- `stateful-service-recovery-matrix.md`: one-page classification of backup/restore versus relocation priorities
- `storage-options.md`: where XFS, ZFS, and NFS fit in the stack
- `network-storage-integration.md`: how shared network storage could fit the current live services
- `storage-capacity-inventory-2026-03-23.md`: observed NFS and local-node storage capacity snapshot
- `node-loss-tolerance-options.md`: realistic paths from restart durability toward node-loss tolerance
- `node-loss-tolerance-next-steps.md`: concrete near-term path for backup/restore and OpenClaw relocation work
- `internal-service-exposure.md`: internal-only service access model
- `mac-studio-inference.md`: decision and switch path for using a Mac Studio as the primary external inference host
- `image-distribution.md`: current image import path and registry migration plan
- `secrets-and-dr.md`: local secret handling and disaster recovery notes
- `runbooks/backup-restore-local-pv-services.md`: validated first backup/restore path for the local-PV-backed v2 services
- `runbooks/`: operational steps once manifests and services land
