# Technique Catalog

The technique catalog is the fastest path for getting NotebookLM-curated
methodology knowledge into Glasslab without turning NotebookLM itself into a
runtime dependency.

## Purpose

The catalog stores structured technique cards that can enrich:

- interpretation
- methodology drafting
- preflight
- autoresearch mutation choices

The runner still consumes bounded `MethodSpec` objects. The catalog is a
knowledge layer, not an execution surface.

## Current Flow

- NotebookLM or a human produces technique cards
- `workflow-api` imports them into the technique catalog
- interpretation matches cards against the current intake text
- matched cards enrich:
  - model-family hints
  - metric hints
  - loss/distance hints
  - validation-strategy hints
  - Python package hints
  - workflow/resource-profile hints
- the bounded runner continues from:
  - `TechniqueKnowledge`
  - `MethodSpec`
  - approved workflow run

## Current Endpoints

- `POST /technique-catalog/import`
- `GET /technique-catalog`
- `GET /technique-catalog/{technique_id}`

## Import Shape

The import route accepts a JSON payload like:

```json
{
  "import_source": "notebooklm-manual-export",
  "cards": [
    {
      "name": "PyTorch Vision Transformer",
      "aliases": ["vit", "vision transformer"],
      "problem_types": ["multiclass_classification"],
      "algorithm_family": "transformers",
      "specific_algorithms": ["vit_b16"],
      "loss_functions": ["contrastive_loss"],
      "validation_strategies": ["holdout", "k_fold_cv"],
      "primary_metrics": ["accuracy", "f1_score"],
      "python_packages": ["torch", "timm"],
      "gpu_required": true,
      "resource_profile": "gpu-small",
      "workflow_ids": ["gpu-experiment"],
      "default_execution_inputs": {
        "pair_strategy": "artist_positive_negative_pairs",
        "evaluation_protocol": "same_artist_verification",
        "label_field": "artist_id"
      },
      "common_failure_modes": ["overfitting_without_stratified_split"],
      "source_refs": ["notebooklm://vision-transformer-card"]
    }
  ]
}
```

## Current Matching Behavior

The first pass is deliberately simple:

- match by name
- match by aliases
- match by specific algorithms
- match by Python package names
- match by problem-type strings
- match by explicit intake `technique_tags`

This is enough to start enriching bounded runner state without depending on a
larger semantic retrieval layer yet.

Technique cards can also carry bounded `default_execution_inputs`.

This is the current path for task-specific runner hints like:

- `pair_strategy`
- `evaluation_protocol`
- `label_field`
- `image_field`
- `negative_sampling_strategy`

Those values are merged into `MethodSpec.execution_inputs` without letting the
catalog author arbitrary manifests.

## Explicit Tags

Intakes can now carry explicit `technique_tags`.

This is the current low-friction way to reduce dependence on lucky natural
language phrasing. Tags let the operator or upstream chat layer say things like:

- `dreamsim`
- `metric_learning`
- `vision_transformer`
- `artist_aware_split`

Those tags are stored on the intake record and participate in catalog matching
alongside the raw request text.

## Autoresearch Use

The catalog no longer only affects interpretation.

Autoresearch now also consumes matched technique cards when it drafts bounded
methodology variants. In practice that means:

- imported technique cards can introduce candidate models
- imported cards can contribute package requirements
- imported cards can suggest loss/distance objectives
- imported cards can steer validation strategy variants

This keeps the mutation surface bounded while making methodology drafting less
dependent on ad hoc text hints.

## Live Validation

This path has now been validated live on `.44` with a DreamSim-style technique
card plus explicit intake tags.

That live run confirmed:

- explicit `technique_tags` persist on the intake record
- a matched catalog card can now override weaker workflow hints from the
  interpretation model path
- the interpreted preferred workflow can move to `gpu-experiment`
- the resulting design inherits that workflow choice
- autoresearch can start and draft catalog-driven methodology variants from the
  matched card
- the design can become `ready_for_run` when the card also supplies bounded
  execution defaults
- `!run` can launch a real `gpu-experiment` Job from those defaults
- `!launch-iteration` can launch an autoresearch GPU run using the approved
  runner model template while still preserving technique-specific hints like
  `vision_transformer` in the methodology draft

## Scope

This is intentionally the fast path, not the final design.

Later improvements can include:

- richer schema normalization
- better retrieval/ranking over the catalog
- tighter integration with textbook-derived methodology knowledge
- stronger mapping from catalog cards into bounded workflow templates
