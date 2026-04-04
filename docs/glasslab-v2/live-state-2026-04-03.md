# Live State 2026-04-03

This note records the live in-lab validation for the technique-catalog follow-on
that added explicit intake tags, made autoresearch consume matched technique
cards directly, and hardened the bounded runner path so a runner-first session
can launch real runs without staging papers first.

## Live rollouts

- `workflow-api` rolled live on `.44` as
  `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.67-local`
- `research-command-router` rolled live on `.44` as
  `ghcr.io/offensivegeneric/glasslab-research-command-router:0.1.4`
- local commits behind these rollouts:
  - `e080db0` `Prioritize technique cards over weak workflow hints`
  - `061ce19` `Let technique cards fill bounded run inputs`
  - `cc452e0` `Upsert technique cards by name`
  - `0d74239` `Prefer richest technique card per name`

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
- the resulting design became `ready_for_run`
- `!preflight` returned no blocking issues
- `!run` submitted a real `gpu-experiment` Kubernetes Job
- autoresearch campaign creation succeeded
- methodology drafting produced catalog-driven variants
- `!launch-iteration` submitted a real autoresearch `gpu-experiment` Job
- `!decide-latest` recorded a durable `keep` decision

The first catalog-driven drafted variants included:

- models:
  - `vision_transformer`
  - `vit`, `clip`
- packages:
  - `torch`
  - `timm`
- notes:
  - `technique-catalog variant from DreamSim Transformer Similarity`

The bounded runner sequence that now works live through the deterministic ingress
is:

- `!research replicate DreamSim visual similarity metric with PyTorch and timm`
- `!design`
- `!preflight`
- `!run`
- `!start-autoresearch`
- `!draft-methodologies`
- `!launch-iteration`
- `!decide-latest`
- `!model-comparison`

## Meaning

The technique catalog is no longer just a passive enrichment layer.

In the current live path it can now:

- use explicit intake tags to strengthen card matching
- override weaker model-drafted workflow/resource hints
- steer the design toward an approved execution template
- seed autoresearch methodology variants from imported technique knowledge
- provide bounded execution defaults like dataset URI, evaluation target, and
  training notes that make the design `ready_for_run`

The runner-first path is now materially real:

- a natural-language session goal can bootstrap an intake automatically
- `!design` can auto-create the needed intake and interpretation state
- `!run` can create a bounded GPU run from `MethodSpec`
- `!launch-iteration` can create an autoresearch GPU run using an allowed runner
  template while preserving technique-specific method hints in inputs
- completed runs feed into `!decide-latest` and `!model-comparison`

## Remaining caveats

- `workflow-api /healthz` still reports stale build provenance on `.44`
  even when the live behavior matches the new code
- the bounded DreamSim path is now usable, but it still relies on a good
  imported technique card for executable defaults
- `!research` still routes through the literature-oriented session-start path,
  so the paper queue can remain noisy even though the runner-first path no
  longer depends on it
- the current GPU runner still writes a stub-style success metric
  (`contract_readiness`) rather than a real DreamSim evaluation result
- the broader comparison path will not become genuinely useful until multiple
  technique-card-backed variants complete with meaningful metrics
