# Workflow Registry

The workflow registry is the approval boundary for Glasslab v2.

Every definition under `services/workflow-registry/definitions/` is a reviewed workflow family entry. `workflow-api` should reject any run request that does not map cleanly to one of these definitions.

## Required fields

- `workflow_id`: stable machine-readable identifier
- `display_name`: short operator-facing name
- `workflow_family`: broad family such as tabular benchmark or replication-lite
- `description`: narrow statement of what the workflow is allowed to do
- `required_inputs`: explicit input list with names, types, required flag, and description
- `allowed_models`: models the workflow may request
- `runner_image`: approved executor image
- `evaluator_type`: deterministic evaluator category
- `expected_artifacts`: required and optional artifact names
- `resource_profile`: one explicit profile for the initial implementation
- `approval_tier`: policy tier for unattended or operator-triggered execution

## How to add a workflow family

1. Copy an existing JSON definition in `services/workflow-registry/definitions/`.
2. Change the identifier, description, inputs, allowed models, and artifact contract.
3. Keep the runner image and approval tier explicit.
4. Validate the new entry against the schema in `services/common/schemas/workflow_registry.py`.
5. Add or update service tests before using the workflow through `workflow-api`.

No plugin loading, runtime code generation, or implicit model expansion belongs here.
