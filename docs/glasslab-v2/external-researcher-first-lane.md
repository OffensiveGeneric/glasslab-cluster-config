# External Researcher First Lane

This note narrows issue `#47` from a general hardening gap list into one concrete first-access model.

The right first step is not broad outside-user cluster access.

It is one bounded researcher lane with explicit limits and admin-owned control points.

## Recommended First Lane

Create one outside-researcher lane with these properties:

- one dedicated namespace for reviewed workloads
- CPU-first by default
- no direct access to core v2 services
- reviewed image onboarding only
- artifact delivery through the existing backend path

This is enough to offer something more valuable than a home laptop without pretending the cluster is already mature multi-tenant infrastructure.

## Core Constraints

### Access

- no broad worker-node SSH
- no direct access to `workflow-api`, Postgres, NATS, or MinIO internals
- no direct OpenClaw exposure as the primary researcher interface

### Scheduling

- prefer CPU-first placement
- avoid core-service nodes where practical
- do not offer GPU as part of the first lane by default

### Workload Scope

- reviewed workloads only
- bounded workflow classes only
- no arbitrary shell-driven cluster control surface

### Secrets

- project-scoped secrets only
- no reuse of admin or shared backend secrets

## Suggested Kubernetes Shape

The first lane should eventually include:

- one namespace such as `glasslab-guest-a`
- one `ResourceQuota`
- one `LimitRange`
- one default-deny `NetworkPolicy`
- one scoped image-pull / service-account model

That is the minimum credible isolation boundary.

## Suggested Initial Scheduling Policy

For the first lane:

- CPU workloads only
- explicit node placement away from the current core v2 service concentration where practical
- no GPU requests unless a later reviewed GPU lane is introduced

This keeps the first access story simple and avoids coupling outside-user onboarding to the unresolved `node02` transition.

## Suggested Operational Model

The first lane should still be admin-mediated.

That means:

- researcher submits a reviewed workload request
- admins map it into the bounded lane
- artifacts are returned through the backend path

This is still much stronger than "run it on your laptop," but avoids pretending the cluster is already self-service.

## Graduation Criteria For A Broader Lane

Do not broaden access until these are explicit:

- authentication path
- quota and fairness policy
- image onboarding policy
- secret-scoping policy
- GPU allocation policy

## Bottom Line

The first hardened outside-researcher access model should be:

- one bounded namespace
- one reviewed CPU-first execution lane
- no direct backend-service exposure
- no GPU by default

That gives Glasslab a credible first user-isolation story without overselling maturity.

## References

- `external-researcher-hardening-gaps.md`
- `external-researcher-access-primitives.md`
- `external-researcher-offer-profiles.md`
