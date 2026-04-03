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

This is enough to start enriching bounded runner state without depending on a
larger semantic retrieval layer yet.

## Scope

This is intentionally the fast path, not the final design.

Later improvements can include:

- richer schema normalization
- better retrieval/ranking over the catalog
- tighter integration with textbook-derived methodology knowledge
- stronger mapping from catalog cards into bounded workflow templates
