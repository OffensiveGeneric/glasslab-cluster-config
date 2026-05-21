# Metric Search Workflow Display Report

This report summarizes the separate `glasslab-metric-search` project as a
Glasslab workflow family. It is intended to sit beside the infrastructure
diagram and explain what a GPU research workflow is supposed to do.

## Project Purpose

`glasslab-metric-search` is the workload-side project for contrastive
representation learning and metric-learning search.

Its research target is:

- unseen-class generalization
- CIFAR-100 seen/unseen validation
- ArtBench-style metric-learning runs
- bounded mutation over metric-learning configuration
- comparable evidence bundles that Glasslab can rank, report, and iterate on

## Boundary Between Repos

| Repo | Owns |
| --- | --- |
| `glasslab-cluster-config` | sessions, run creation, Kubernetes scheduling, status, artifact indexing, comparison, reports |
| `glasslab-metric-search` | dataset bindings, model/loss/trainer/evaluator behavior, search spaces, candidate mutation logic |

The contract between them is the run spec emitted and consumed by the
metric-search runner.

## Workflow Shape

| Stage | Metric-search responsibility | Glasslab responsibility |
| --- | --- | --- |
| Candidate definition | define config/search-space candidate | create run record and run spec |
| Dataset binding | understand dataset schema and splits | mount or provide dataset location |
| Training | run model/loss/miner/trainer | schedule the GPU Job |
| Evaluation | compute retrieval and clustering metrics | collect and index artifacts |
| Baselines | produce comparable baseline outputs | compare across run bundles |
| Report material | write run-local metrics and summaries | generate operator-facing report |
| Mutation | expose allowed config changes | decide next bounded variant |

## Metric Search Components

| Component | Path | Role |
| --- | --- | --- |
| configs | `configs/` | datasets, augmentations, search spaces, scheduler/loss config |
| runner scripts | `scripts/run_experiment.py`, `scripts/train.py`, `scripts/evaluate.py` | end-to-end run, training, evaluation |
| search logic | `search/` | run spec, validation, mutation, selection |
| data loaders | `src/data/` | CIFAR-100 and dataset handling |
| models | `src/models/` | backbone/model registry |
| losses | `src/losses/` | contrastive and proxy losses |
| miners | `src/miners/` | tuple/negative mining strategy |
| metrics | `src/metrics/` | grouped recall, OPIS, clustering metrics |
| evaluators | `src/evaluators/` | evaluation pipeline |
| benchmarks | `benchmarks/art_retrieval.py` | art retrieval benchmark helpers |
| container | `Dockerfile` | image boundary for Kubernetes jobs |

## Intended Runtime Shape

One metric-search candidate maps to one Kubernetes Job.

Expected job shape:

| Field | Value |
| --- | --- |
| namespace | `glasslab-v2` |
| workflow/workload ID | `metric-search-v0` |
| container | `ghcr.io/offensivegeneric/glasslab-metric-search:<commit_sha>` |
| command | `python3 scripts/run_experiment.py` |
| GPU | `nvidia.com/gpu: 1` |
| CPU request | about `8` |
| memory request | about `32Gi` |
| dataset mount | `glasslab-shared-datasets` PVC |
| artifact mount | `glasslab-shared-artifacts` PVC |
| artifact root | `/mnt/artifacts/<run_id>` |

## Run Spec Contract

Required run-spec fields:

- `run_id`
- `parent_run_id`
- `base_commit`
- `submitted_by`
- `workflow_family`
- `search_space_id`
- `dataset`
- `resources`
- `budget`
- `config`

Example resource shape:

```json
{
  "gpu_count": 1,
  "cpu_count": 8,
  "memory_gb": 32
}
```

## Artifact Contract

Each run should write:

- `run_spec.json`
- `run_manifest.json`
- `config.json`
- `metrics.json`
- `status.json`
- `report.md`
- `artifacts_index.json`
- `logs/runner.log`

## Scientific Validation Focus

Metric-search is a good proving workflow because it forces Glasslab to handle
real GPU execution, baseline comparisons, run artifacts, and evidence-based
iteration.

The scientific validation focus is:

- define a clear retrieval-gallery contract
- record gallery size, class grouping, and partial-evaluation warnings
- compare trained runs to random, shuffled-label, frozen ResNet, DINO, and CLIP
  baselines
- separate smoke-test success from scientific claims
- preserve enough artifacts to make the comparison reviewable later

## Diagram Source

Use this Mermaid block as the source for an image generator or diagram renderer.

```mermaid
flowchart LR
  session[Glasslab research session] --> plan[bounded metric-search plan]
  plan --> api[workflow-api]
  api --> spec[run_spec.json]
  spec --> job[Kubernetes Job<br/>metric-search-v0]
  job --> image[metric-search image]
  job --> data[(shared datasets PVC)]
  job --> gpu[GPU worker<br/>nvidia.com/gpu=1]
  image --> runner[scripts/run_experiment.py]
  runner --> configs[configs/search_spaces/*.yaml]
  runner --> model[src/models + src/losses + src/miners]
  runner --> eval[src/metrics + src/evaluators]
  eval --> bundle[(run bundle<br/>/mnt/artifacts/run_id)]
  bundle --> metrics[metrics.json]
  bundle --> report[report.md]
  bundle --> index[artifacts_index.json]
  metrics --> compare[comparison / evaluator]
  compare --> decision[operator decision]
  decision --> mutation[next bounded variant]
```

## Visual Encoding Recommendation

For the metric-search diagram:

- blue: Glasslab control-plane ownership
- green: metric-search repo/runtime ownership
- orange: run-spec contract boundary
- purple: GPU execution
- gray: artifact and dataset storage
- red accent only for validation caveats

