# External Researcher Access Primitives

This note maps the outside-researcher hardening conversation onto concrete technical primitives.

The question is not just "what are the gaps?" It is "what needs to exist in the repo and cluster before outside-researcher access is credible?"

## 1. Access Boundary

Needed:

- a single explicit access path
- strong authentication
- documented review flow for new users

Likely implementation shapes:

- VPN or tailnet access for approved operators only
- or an authenticated reverse-proxy path for narrow services

Not recommended:

- exposing internal ClusterIP services directly
- distributing broad SSH access to worker nodes

## 2. Namespace Boundary

Needed:

- one bounded namespace per outside-researcher lane or project
- default-deny assumptions around what can talk to what

Concrete Kubernetes primitives:

- `Namespace`
- `ResourceQuota`
- `LimitRange`
- `NetworkPolicy`

## 3. Scheduling Boundary

Needed:

- explicit statement of which nodes or workload classes are eligible
- no accidental contention with core v2 services

Concrete Kubernetes primitives:

- `nodeSelector`
- node affinity / anti-affinity
- taints / tolerations where needed
- explicit GPU resource requests for reviewed GPU lanes only

## 4. Image Boundary

Needed:

- approved image onboarding path
- explicit rule for what images outside workloads may use

Concrete implementation:

- reviewed image build/import or registry path
- allowlist of base images or workflow-owned images
- no ad hoc arbitrary unreviewed image execution as the default

## 5. Secret Boundary

Needed:

- outside workloads should get only project-scoped secrets
- internal service credentials must stay admin-controlled

Concrete Kubernetes primitives:

- namespace-scoped `Secret`
- service-account-scoped access only
- no shared cluster-admin style secret reuse

## 6. Artifact Boundary

Needed:

- explicit statement of where outputs land
- explicit retention expectations

Concrete implementation:

- workflow artifacts written through the existing backend path
- deterministic artifact index surfaced by `workflow-api`
- no vague "files might still be on some node" posture for outsider-facing runs

## 7. Operational Review Boundary

Needed:

- every outside-researcher run class should have a clear approval rule
- unattended execution should remain tier-gated

Concrete implementation:

- approval-tier checks in `workflow-api`
- bounded workflow registry entries
- operator review for anything outside the pre-approved path

## Minimum Credible First Offer

The minimum credible first offer is not self-service cluster tenancy.

It is:

- one reviewed execution lane
- one bounded namespace or equivalent backend-owned boundary
- quotas and limits
- artifact delivery
- no direct access to core backing services

That is enough to provide something stronger than a laptop without pretending the environment is already mature multi-tenant infrastructure.

## References

- `external-researcher-what-we-can-offer-now.md`
- `external-researcher-hardening-gaps.md`
- `operator-access-options.md`
- `internal-service-exposure.md`
