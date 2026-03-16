# V2 Services And Contracts

Glasslab v2 treats workflow execution as a contract-driven pipeline.

## Service placement

- `workflow-api` owns request intake, registry lookup, validation, run manifest creation, persistence, and the job submission boundary.
- `evaluator` compares multiple run artifact bundles after execution completes.
- `reporter` converts manifests, metrics, and evaluator output into a stable Markdown memo.
- Kubernetes Jobs remain the bounded execution layer.

## Canonical artifact contract

Every workflow must emit these artifacts:

- `run_manifest.json`
- `config.json`
- `metrics.json`
- `artifacts_index.json`
- `report.md`
- `status.json`
- `logs/`

Optional artifacts are declared per workflow definition under `expected_artifacts.optional` in the workflow registry.

## Run manifest intent

The run manifest is the canonical record of what was requested, what was approved, and what runner image and resource profile were selected. Evaluators and reporters should rely on this record instead of reconstructing intent from logs.
