# Bounded-Agent Live Enable Criteria

This note narrows the four bounded service issues:

- interpretation-agent
- intake-agent
- assessment-agent
- design-agent

The repo already contains for all four:

- service scaffold
- `workflow-api` feature-flagged integration
- fail-closed validation path
- deployment manifests
- build/push and deploy runbooks

What remains is no longer architecture.

What remains is the live-enable milestone.

## Shared Live-Enable Criteria

Each bounded-agent issue should be considered materially advanced past the repo-implementation phase when these are true:

1. image is built and pullable by the cluster
2. deployment and service are live in `glasslab-v2`
3. the corresponding feature flag is enabled
4. the relevant `workflow-api` endpoint is exercised live
5. `stage-record-created ... source=agent` is observed for that stage
6. fail-closed fallback is still verified by disabling the service or returning invalid data

## Stage-Specific Endpoint Map

### Interpretation

- service: `glasslab-interpretation-agent`
- feature flag:
  - `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_ENABLED=true`
- endpoint to exercise:
  - `POST /interpretations/from-latest-intake`

### Intake

- service: `glasslab-intake-agent`
- feature flag:
  - `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_ENABLED=true`
- endpoint to exercise:
  - `POST /intakes`

### Assessment

- service: `glasslab-assessment-agent`
- feature flag:
  - `GLASSLAB_WORKFLOW_API_ASSESSMENT_AGENT_ENABLED=true`
- endpoint to exercise:
  - `POST /replicability-assessments/from-latest-interpretation`

### Design

- service: `glasslab-design-agent`
- feature flag:
  - `GLASSLAB_WORKFLOW_API_DESIGN_AGENT_ENABLED=true`
- endpoints to exercise:
  - `POST /design-drafts/from-latest-intake`
  - `POST /design-drafts/from-latest-assessment`

## Shared Anti-Pattern

Do not enable all four at once.

Use the rollout order already documented in:

- `stage-agent-rollout-order.md`

That means:

1. interpretation
2. intake
3. assessment
4. design

## What Should Not Keep These Issues Open

Do not keep the individual issues open merely because:

- the service is not yet model-perfect
- later prompt tuning may still happen
- stronger models may be tried later

Once a stage is live-deployed, feature-flagged, verified, and observed to fail
closed correctly, the remaining work is iterative quality improvement, not the
original implementation issue.

## Bottom Line

These four issues are now live-rollout issues, not architecture issues.

## References

- `runbooks/deploy-bounded-agents.md`
- `stage-agent-rollout-order.md`
- `runbooks/deploy-v2.md`
