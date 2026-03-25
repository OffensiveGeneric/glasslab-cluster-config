# External Researcher Hardening Gaps

This note records what still needs to be hardened before Glasslab should be treated as a good environment for outside researchers to run workloads directly.

## Short Answer

The main gap is not raw compute.

The main gap is operational maturity for outside-user access.

## Gaps

### 1. No Clean Multi-Tenant Access Model

Current state:

- access is still lab-admin oriented
- services are internal-only by default
- there is no clean self-service researcher lane documented

Needed:

- explicit access model
- user / team boundary
- reviewed ingress or tunnel path
- strong authentication plan

### 2. No Resource Quota / Fairness Policy

Current state:

- the repo does not describe outside-user quotas or reservation policy
- core services and legacy workloads already occupy parts of the cluster

Needed:

- namespace quotas
- requests / limits policy
- GPU access policy
- priority policy for core services versus guest workloads

### 3. GPU Capacity Is Not Yet Cleanly Reclaimable

Current state:

- `node02` still has the legacy `vllm` pod reserving its GPU
- GPU nodes are present, but not yet presented as a clean outside-user pool

Needed:

- decide whether legacy `vllm` is retired or retained as fallback
- define which GPU nodes, if any, can be offered to guest workloads
- define approved GPU workload classes

### 4. Storage / Artifact Expectations Are Still Pragmatic

Current state:

- v2 still relies on local-PV and practical storage choices in several places
- disaster recovery and failover posture are still evolving

Needed:

- clear artifact retention expectations
- documented backup / restore promises
- clear statement of what data is durable and what is not

### 5. Image / Workload Supply Path Is Still Admin-Centric

Current state:

- custom image flow still has `.44`-era assumptions
- there is no documented outsider-safe image onboarding path

Needed:

- approved registry flow
- image review policy
- namespace-scoped image pull process

### 6. Secret / Credential Model Is Not Outsider-Ready

Current state:

- secrets and deploy flow are still controlled operationally by lab admins
- there is no documented pattern for outside-user secret injection

Needed:

- a clear secret boundary
- per-project or per-tenant secret model
- explicit guidance on what outside workloads may access

### 7. OpenClaw Is Not An Outside-Researcher Control Surface Yet

Current state:

- OpenClaw is intentionally narrow
- current tool path is still being revalidated on the Mac-backed model side

Needed:

- do not treat OpenClaw as the primary outside-researcher entry point yet
- keep it as an internal operator shell until the control surface and authentication path are more settled

## Recommended Order

Before offering broader outside-researcher access:

1. decide the access path
2. decide the quota / fairness model
3. retire or define the role of legacy `node02` `vllm`
4. clarify image onboarding
5. clarify storage and artifact guarantees
6. clarify secret boundaries

## Current Recommendation

Until those gaps are addressed, the right outside-researcher model is:

- reviewed workloads
- admin-mediated submission
- bounded approved workflows
- artifact delivery rather than self-service cluster control

## References

- `security-model.md`
- `../machine-state-2026-03-24.md`
- `../live-state-2026-03-24.md`
