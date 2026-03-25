# Glasslab v2

Glasslab v2 turns the current Titanic-specific path into an explicit, registry-driven workflow platform.

Current live validation reference:

- `../live-state-2026-03-23.md`
- `../live-state-2026-03-24.md`
- `../live-state-2026-03-25.md`
- `../machine-state-2026-03-24.md`
- `../machine-state-2026-03-25.md`

Canonical planning and architecture:
- `overview.md`: repo-level architecture and control flow
- `workflow-registry.md`: approved workflow family format
- `services.md`: canonical run and artifact contract
- `research-pipeline-target.md`: the intended end-state product shape for Glasslab research workflows
- `stage-agent-pipeline.md`: specialized backend agent roles, handoffs, and why OpenClaw should stay at the edge
- `stage-agent-rollout-order.md`: recommended stage-by-stage enablement order for the bounded-agent pipeline
- `bounded-agent-live-enable-criteria.md`: shared live rollout milestone for intake, interpretation, assessment, and design agents
- `autonomous-research-lane.md`: current bounded path for source scouting, ranker-assisted intake, and unattended digest work
- `doc-audit-2026-03-24.md`: which v2 docs are still canonical, which are historical scaffolding, and which map to tracker work
- `intake-design-run-implementation-plan.md`: first concrete backend plan for intake -> design draft -> validation run
- `model-improvement-options.md`: stronger model vs ranker vs control-surface vs backend decomposition
- `ranker-service-shape.md`: first concrete API and ownership boundary for a bounded ranker service
- `ranker-integration-plan.md`: how `workflow-api` should consume the ranker while keeping ranking advisory and fail-closed
- `ranker-implementation-checklist.md`: concrete checklist for wiring the ranker into intake handling behind a feature flag
- `mac-studio-inference.md`: decision and switch path for using a Mac Studio as the primary external inference host
- `mac-service-host-boundary.md`: why the Macs should stay outside kubeadm and act as service hosts first
- `mac-service-host-close-criteria.md`: when the Mac integration issue should be considered materially resolved as a service-host decision
- `ollama-native-openclaw.md`: why remote Ollama should use native OpenClaw provider mode instead of `/v1` when tool calling matters
- `node02-interpretation-agent-experiment.md`: why the first cluster-side stage-agent experiment should be a bounded interpretation worker on `node02`
- `node02-role-decision.md`: explicit decision rule for retiring legacy `node02` `vllm` and reclaiming the GPU lane
- `interpretation-agent-service.md`: concrete contract and ownership boundary for the first in-cluster stage-agent service
- `stage-agent-api-changes.md`: concrete `workflow-api`, service-contract, and config changes needed for the staged backend-agent path
- `evaluation-boundary.md`: why evaluation should stay deterministic first and where later narrative enrichment could fit
- `evaluation-implementation-checklist.md`: concrete wiring checklist for the deterministic evaluator path
- `evaluation-close-criteria.md`: when the deterministic evaluation issue should be considered materially resolved
- `run-preparation-boundary.md`: why canonical run preparation should remain inside `workflow-api`
- `run-preparation-implementation-checklist.md`: concrete checklist for preserving the deterministic manifest-derivation path
- `run-preparation-close-criteria.md`: when the deterministic run-preparation issue should be considered materially resolved
- `execution-boundary.md`: why execution remains deterministic and backend-owned instead of becoming a free-form agent
- `execution-implementation-checklist.md`: concrete checklist for preserving the deterministic execution path
- `reporting-boundary.md`: why reporting should stay grounded in explicit artifacts and deterministic rendering first
- `reporting-close-criteria.md`: when the deterministic reporting issue should be considered materially resolved
- `reporting-implementation-checklist.md`: concrete wiring checklist for the deterministic reporter path
- `resume-next-session-2026-03-24.md`: concise checkpoint for resuming after the `qwen3:30b` pull and Mac-native tool evaluation
- `qwen-fit-for-stage-agents.md`: where the current local Qwen path is useful for backend agents and where it is not
- `approval-tier-unattended-ops-plan.md`: concrete plan for unattended digests and approved reruns behind approval tiers
- `workflow-api-schedules.md`: current stored schedule endpoints for digests and approved reruns
- `schedule-worker-plan.md`: bounded worker shape for executing due schedules after re-validation
- `schedule-execution-boundaries.md`: fail-closed execution rules for stored schedules and future `run-now` support
- `schedule-implementation-checklist.md`: concrete backend checklist for digest workers, approved reruns, audit records, and eventual `run-now`
- `operator-access-options.md`: narrowed decision between Tailscale or reverse proxy for stable operator-facing access
- `operator-access-recommendation.md`: concrete recommendation to expose only OpenClaw through a narrow authenticated operator path
- `operator-access-close-criteria.md`: when the operator-access decision issue should be considered materially resolved
- `whatsapp-dedicated-account-migration.md`: why the current self-chat bootstrap path should move to a dedicated lab-assistant account before broader researcher use
- `openclaw-runtime-portability.md`: what has and has not been reduced in the `.44`-special OpenClaw runtime path
- `remote-admin-path.md`: why off-site operation through `glasslab.org -> .44` reduces friction without changing `.44`'s canonical admin role
- `external-researcher-what-we-can-offer-now.md`: practical current answer for what outside researchers can safely use today
- `external-researcher-hardening-gaps.md`: what must be hardened before outside researchers should be treated as first-class cluster users
- `external-researcher-offer-profiles.md`: concrete outside-researcher offer lanes and why "one worker node" is the wrong framing
- `external-researcher-access-primitives.md`: concrete Kubernetes and access-control primitives needed before broader outside-researcher use
- `external-researcher-first-lane.md`: concrete first outside-researcher lane shape instead of broad self-service cluster access
- `tool-choice-exposure-options.md`: realistic paths for issue `#11` and why runtime YAML alone is not enough
- `tool-choice-patch-experiment.md`: bounded experiment plan for carrying a tiny OpenClaw patch only if pinned-tool evaluation is still worth it
- `provisioner-dependence-inventory.md`: splits the remaining `.44` dependence into image, runtime, secret, and admin-context buckets
- `provisioner-dependence-close-criteria.md`: defines when the remaining `.44` dependence should still be considered a real epic versus an intentional admin boundary

Still-current supporting design notes:
- `no-arg-vs-argumented-tools.md`: why the current safe operator path is mostly no-arg tools, what argumented tools would need to prove, and the current safety rules for repo-managed intake templates
- `bounded-agent-architecture.md`: earlier backend-agent framing that now points toward `stage-agent-pipeline.md`
- `next-no-arg-operator-actions.md`: original no-arg action ladder that is now partly implemented and mainly useful as historical context

Operational and infrastructure references:
- `cluster-primitives-gap-audit.md`: missing infrastructure primitives and next actions
- `storage-and-state.md`: storage posture and persistence expectations
- `stateful-service-recovery-matrix.md`: one-page classification of backup/restore versus relocation priorities
- `node-loss-tolerance-phased-plan.md`: phased execution order for moving from restart durability toward node-loss tolerance
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
- `openclaw-shared-state-decision.md`: decision rule for whether the OpenClaw shared-state experiment should change the default storage path
- `runbooks/`: operational steps once manifests and services land
