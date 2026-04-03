# Live State 2026-04-03

This note records the live in-lab validation for the technique-catalog follow-on
that added explicit intake tags and made autoresearch consume matched technique
cards directly.

## Live rollout

- `workflow-api` rolled live on `.44` as
  `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.61-local`
- local commit behind this rollout:
  - `e080db0` `Prioritize technique cards over weak workflow hints`

## What was validated live

A DreamSim-style technique card was imported through:

- `POST /technique-catalog/import`

A fresh session and intake were then created with explicit tags:

- `dreamsim`
- `visual_similarity`
- `transformers`
- `contrastive_loss`

The resulting live behavior was:

- interpretation candidate workflows included `gpu-experiment`
- interpretation `preferred_workflow_id` became `gpu-experiment`
- interpretation `preferred_resource_profile` became `gpu-small`
- interpretation `gpu_required` was `true`
- the matched catalog ids were persisted in `technique_knowledge.catalog_technique_ids`
- the resulting design also selected `gpu-experiment`
- autoresearch campaign creation succeeded
- methodology drafting produced catalog-driven variants

The first catalog-driven drafted variants included:

- models:
  - `vision_transformer`
  - `vit`, `clip`
- packages:
  - `torch`
  - `timm`
- notes:
  - `technique-catalog variant from DreamSim Transformer Similarity`

## Meaning

The technique catalog is no longer just a passive enrichment layer.

In the current live path it can now:

- use explicit intake tags to strengthen card matching
- override weaker model-drafted workflow/resource hints
- steer the design toward an approved execution template
- seed autoresearch methodology variants from imported technique knowledge

## Remaining caveats

- `workflow-api /healthz` still reports stale build provenance on `.44`
  even when the live behavior matches the new code
- the DreamSim-style design is still `needs_review` because the dataset and
  other run inputs are not automatically resolved from the technique card alone
- the catalog can now steer workflow choice and methodology drafting, but it
  does not yet fully materialize executable dataset/repository/evaluation
  contracts for every technique family
