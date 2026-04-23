# Generic Experiment Contract

This document proposes the Glasslab-side abstraction that should support new
research workloads without creating bespoke API endpoints for each idea.

The core rule is:

- Glasslab should expose one generic experiment-run contract
- workload-specific behavior should be expressed as data and registry entries
- new research ideas should not require new backend endpoint shapes

## Why This Exists

The wrong direction is:

- one new API surface per project
- one handcrafted workflow family per domain idea
- one-off result parsing logic per experiment type

That turns the platform into an accumulation of special cases.

The right direction is:

- one generic run submission path
- one generic result-ingest path
- one workload registry layer
- one evaluator contract model

## Design Goal

Support workloads like:

- tabular baselines
- metric-learning search
- bounded vision experiments
- retrieval benchmark runs

without changing the public API shape each time.

## Core Abstraction

The platform should separate:

- **experiment type**
- **workload definition**
- **run submission**
- **result ingestion**

### Experiment type

A coarse category such as:

- `python-job`
- `gpu-training-job`
- `evaluation-job`

This is about execution shape, not research topic.

### Workload definition

A registry entry that declares:

- allowed schema
- runner image expectations
- resource bounds
- artifact contract
- metric contract
- evaluator binding

Examples:

- `tabular-baseline-v1`
- `metric-search-v0`
- `retrieval-eval-v1`

These are workload definitions, not custom APIs.

## Proposed API Shape

The public backend contract should stay generic.

### Submit a run

`POST /experiments/runs`

Request body shape:

```json
{
  "experiment_type": "gpu-training-job",
  "workload_id": "metric-search-v0",
  "parent_run_id": "run-123",
  "campaign_id": "campaign-abc",
  "image_ref": "ghcr.io/offensivegeneric/glasslab-metric-search:928f3be",
  "entrypoint": [
    "python3",
    "scripts/run_experiment.py",
    "--config",
    "/work/configs/search_spaces/art_metric_proxy_v0.yaml",
    "--output-dir",
    "/outputs/run"
  ],
  "config_payload": {
    "workflow_family": "metric-search",
    "search_space_id": "art-metric-proxy-v0"
  },
  "dataset_bindings": {
    "train_uri": "s3://datasets/artbench/train.parquet",
    "val_uri": "s3://datasets/artbench/val.parquet",
    "test_uri": "s3://datasets/artbench/test.parquet"
  },
  "resources": {
    "gpu_count": 1,
    "cpu_count": 8,
    "memory_gb": 32
  },
  "budget": {
    "max_epochs": 25,
    "max_wallclock_minutes": 180
  },
  "artifact_contract": {
    "required": [
      "run_spec.json",
      "metrics.json",
      "status.json"
    ]
  },
  "metric_contract": {
    "evaluator_type": "art_retrieval_v1"
  }
}
```

### Ingest run results

`POST /experiments/runs/{run_id}/results`

Request body shape:

```json
{
  "terminal_status": "succeeded",
  "metrics": {
    "retrieval_recall_at_10": 0.76,
    "forgery_auroc": 0.73,
    "robustness_score": 0.44,
    "instability_penalty": 0.02
  },
  "artifact_refs": {
    "run_spec": "s3://artifacts/run-123/run_spec.json",
    "metrics": "s3://artifacts/run-123/metrics.json",
    "report": "s3://artifacts/run-123/report.md"
  },
  "runtime": {
    "started_at": "2026-04-22T21:10:00Z",
    "finished_at": "2026-04-22T21:32:00Z",
    "node_name": "node02"
  }
}
```

### Compare runs

Keep comparison generic too.

`POST /experiments/compare`

The comparison behavior should be parameterized by the registered evaluator type,
not by special-case endpoint logic.

## Registry Model

The registry should validate workload definitions, not only topic-specific
"workflow families."

Each workload definition should declare:

- `workload_id`
- `experiment_type`
- `schema_ref` or schema version
- `runner_image_policy`
- `default_entrypoint`
- `resource_bounds`
- `required_artifacts`
- `metric_contract`
- `evaluator_type`
- `approval_tier`

That keeps the API generic while still preserving reviewable execution policy.

## Relationship To Current Workflow Registry

The current `workflow-registry` already contains the right instinct:

- approved execution templates
- explicit inputs
- runner image references
- evaluator types
- expected artifacts

The proposed change is mostly conceptual:

- stop treating each new research workload as if it needs a new API concept
- treat it as a new workload definition under one generic experiment contract

## What Changes In Practice

### What should stay generic

- run submission endpoint
- result ingest endpoint
- comparison endpoint
- session/campaign ownership
- artifact indexing
- run lineage

### What should move into workload definitions

- config schema
- accepted dataset-binding shape
- allowed image/entrypoint pattern
- evaluator bundle
- artifact expectations
- comparison weighting

## How `glasslab-metric-search` should fit

`glasslab-metric-search` should not require a new API family.

It should register something like:

- `workload_id`: `metric-search-v0`
- `experiment_type`: `gpu-training-job`
- `schema_ref`: `glasslab-metric-search RunSpec v0`
- `evaluator_type`: `art_retrieval_v1`

Then the control plane can:

- launch runs from its image
- validate resource/budget bounds
- persist run lineage
- ingest metrics/artifacts
- compare candidates

without any new bespoke endpoint shape.

## Recommended Evolution Path

1. keep the current command/control seam
2. generalize run submission around `experiment_type` + `workload_id`
3. evolve the registry from "workflow family catalog" into "workload definition catalog"
4. keep evaluator contracts explicit and data-driven
5. avoid any per-project orchestration endpoint growth

## Bottom Line

Glasslab should not need one API surface per research idea.

It should provide:

- one generic run contract
- one generic result contract
- one workload-definition registry

That is the abstraction boundary that lets the platform stay stable while new
repos like `glasslab-metric-search` iterate quickly.
