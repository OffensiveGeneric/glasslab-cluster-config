# Stage-Agent API Changes

This note records the concrete API and config changes needed for the imagined backend stage agents to work cleanly.

It exists so the stage-agent issues are not just role descriptions.

## Design Rule

The stage-agent services should not replace `workflow-api`.

They should sit behind it.

That means most API changes should preserve the current public `workflow-api` endpoints while adding:

- internal service contracts
- optional integration flags
- explicit fallback behavior
- stage-specific validation

## `workflow-api` Changes Needed

### 1. Intake-Agent Integration

Current public endpoint can stay:

- `POST /intakes`

Needed additions:

- config flag to enable or disable intake-agent integration
- internal client to call intake-agent before final intake persistence
- explicit fallback to deterministic intake normalization
- logging of agent success / fallback / validation failure

Suggested settings:

- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_INTAKE_AGENT_TIMEOUT_SECONDS`

### 2. Interpretation-Agent Integration

Current public endpoint can stay:

- `POST /interpretations/from-latest-intake`

Needed additions:

- config flag to enable or disable interpretation-agent integration
- internal client to call interpretation-agent
- response validation before persistence
- deterministic fallback to current builder on failure

Suggested settings:

- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_INTERPRETATION_AGENT_TIMEOUT_SECONDS`

### 3. Replicability-Assessment Agent Integration

Current public endpoint can stay:

- `POST /replicability-assessments/from-latest-interpretation`

Needed additions:

- optional agent-backed draft generation before final assessment persistence
- validation that recommended workflow IDs exist in the approved registry
- explicit fallback to deterministic assessment logic

Suggested settings:

- `GLASSLAB_WORKFLOW_API_ASSESSMENT_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_ASSESSMENT_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_ASSESSMENT_AGENT_TIMEOUT_SECONDS`

### 4. Design-Draft Agent Integration

Current public endpoints can stay:

- `POST /design-drafts/from-latest-intake`
- `POST /design-drafts/from-latest-assessment`

Needed additions:

- optional agent-backed draft generation path
- validation that workflow ID, candidate models, and resource profile remain registry-valid
- fallback to deterministic draft generation

Suggested settings:

- `GLASSLAB_WORKFLOW_API_DESIGN_AGENT_ENABLED`
- `GLASSLAB_WORKFLOW_API_DESIGN_AGENT_URL`
- `GLASSLAB_WORKFLOW_API_DESIGN_AGENT_TIMEOUT_SECONDS`

### 5. Run-Preparation Boundary

Current public endpoint can stay:

- `POST /runs/from-latest-design-draft`

Needed design decision:

- decide whether this stage remains fully deterministic
- if any agent help is allowed, keep it read-only advisory and validate every execution-control field in `workflow-api`

The current safest assumption is:

- no new external run-preparation API yet
- keep canonical manifest derivation in `workflow-api`

### 6. Execution Boundary

Current behavior already exists:

- `workflow-api` submits Kubernetes Jobs and stores run state

Needed design decision:

- likely no separate LLM-driven execution API at all
- if a helper service is added later, it should remain deterministic and internal

### 7. Evaluation Boundary

Needed additions are likely smaller:

- stable internal contract between `workflow-api` and `evaluator`
- optional narrative enrichment only after deterministic comparison output exists

Possible public endpoint additions later:

- `POST /evaluations/from-run-set`
- `GET /evaluations/{evaluation_id}`

These are not required for the first agent rollout.

### 8. Reporting Boundary

Needed additions are also likely smaller:

- stable internal contract between `workflow-api` and `reporter`
- explicit report-generation trigger from grounded artifacts

Possible public endpoint additions later:

- `POST /reports/from-run`
- `POST /reports/from-evaluation`
- `GET /reports/{report_id}`

These are not required for the first agent rollout.

## New Internal Service Contracts

The first pass should define internal APIs for the fuzzy stages only.

### intake-agent

- `POST /normalize-intake`

### interpretation-agent

- `POST /interpret-intake`

### assessment-agent

- `POST /assess-interpretation`

### design-agent

- `POST /draft-design`

These should all:

- accept one explicit stage record or request object
- return one bounded draft object
- avoid hidden cross-stage mutation

## Shared Response Metadata

Every stage-agent response should include:

- `request_id`
- `draft`
- `model_backend`
- optional `warnings`

That makes logging and later audit easier.

## Persistence / Audit Changes

`workflow-api` should record, at minimum:

- whether a stage used deterministic logic or agent assistance
- which backend model produced the draft
- whether the agent response was accepted or rejected
- why fallback happened when it did

This can start in logs if no persistent audit field exists yet.

## Kubernetes / Config Changes

Needed config work:

- add internal service manifests for the first stage agents under `kubeadm/glasslab-v2/`
- add non-secret ConfigMap or env wiring for internal agent URLs and timeouts
- add local-secret support if any agent service needs tokens later

## Priority Order

The API changes should be implemented in this order:

1. interpretation-agent integration
2. intake-agent integration
3. replicability-assessment agent integration
4. design-draft agent integration
5. evaluator / reporter trigger contracts
6. any later execution-boundary refinements

## Current Recommendation

Do not try to add all stage-agent APIs at once.

The first concrete implementation should be:

- interpretation-agent service contract
- `workflow-api` feature-flagged integration
- deterministic fallback

That is the smallest change that proves the stage-agent architecture without widening the control surface too early.
