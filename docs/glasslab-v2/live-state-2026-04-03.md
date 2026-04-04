# Live State 2026-04-03

This note records the live in-lab validation for the technique-catalog follow-on
that added explicit intake tags, made autoresearch consume matched technique
cards directly, and hardened the bounded runner path so a runner-first session
can launch real runs without staging papers first.

## Live rollouts

- `workflow-api` rolled live on `.44` as
  `ghcr.io/offensivegeneric/glasslab-workflow-api:0.1.82-local`
- `research-command-router` rolled live on `.44` as
  `ghcr.io/offensivegeneric/glasslab-research-command-router:0.1.6-local`
  and pinned to `node05` for the local-image path
- local commits behind these rollouts:
  - `ec2b9e8` `Replace stale literature queues for active sessions`
  - `3b55b83` `Preserve technique context in GPU runner spec`
  - `16280fc` `Bump runner and workflow-api image tags`
  - local follow-on:
    - generic runner-side technique-contract scoring, reducing DreamSim-specific
      coupling in `bounded_method_score`
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
- `!launch-batch`
- `!decide-batch`
- `!decide-latest`
- `!model-comparison`

The new bounded parallel-launch path was also validated live through the actual
chat command seam:

- `!research replicate DreamSim visual similarity metric with PyTorch and timm`
- `!design`
- `!start-autoresearch`
- `!draft-methodologies`
- `!launch-batch`
- `!decide-batch`

That path returned:

- `route: deterministic-router`
- `command: launch-batch`
- `response_text: Launched 2 autoresearch iteration(s) for the active campaign.`
- two accepted GPU run ids:
  - `a452a9c9d4cb433388f6f9395eaac329`
  - `b61663daf9124881b6fba7d4ca01ea7b`

The batch-decision follow-on is now also live through the same deterministic
command seam:

- `!decide-batch`

That path records decisions for all ready completed iterations in one pass,
using the same bounded decision policy as `!decide-latest`.
The first live validation returned:

- `route: deterministic-router`
- `command: decide-batch`
- `response_text: Recorded 1 autoresearch decision(s) for ready completed iterations.`
- `workflow_api_endpoint: /research-sessions/{session_id}/transitions/decide-autoresearch-batch`
- the recorded decision was `keep`
- the resulting model comparison remained available immediately through
  `!model-comparison`

The latest direct `.44` validation against the same session also confirmed that
fresh autoresearch batch launches preserve technique context all the way into
the GPU runner and decision surface:

- fresh run manifests now use
  `ghcr.io/offensivegeneric/glasslab-gpu-experiment-runner:0.1.6-local`
- fresh runner specs now include:
  - `technique_candidate_models`
  - `technique_baseline_models`
  - `technique_loss_or_distance`
  - `technique_task_type`
  - `technique_metrics`
- the kept DreamSim-style variant scored:
  - `metric_name: bounded_method_score`
  - `best_metric: 0.9688`
  - `best_model: vision_transformer`
  - `technique_alignment_score: 1.0`
- the baseline-style comparison variant scored:
  - `metric_name: bounded_method_score`
  - `best_metric: 0.8438`
  - `best_model: pytorch-template-v1`
- the resulting campaign state became:
  - `status: completed`
  - `recommended_model: vision_transformer`
  - `current_best_methodology_draft_id` pointing at the
    `DreamSim Transformer Similarity` variant

The next runner image for that same path is now intended to use a more generic
technique-contract score:

- runner image target:
  `ghcr.io/offensivegeneric/glasslab-gpu-experiment-runner:0.1.7-local`
- it preserves the same bounded execution/readiness checks
- but replaces the narrower DreamSim-shaped alignment heuristic with a generic
  score over:
  - candidate model contract
  - task contract
  - metric contract
  - objective/loss contract

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
- before `ec2b9e8`, `!research` could keep a stale literature queue attached to
  the active session; `0.1.81-local` now closes that gap live
- direct validation on `.44` showed a new goal:
  - `replicate CLIP image-text retrieval baseline with PyTorch`
  returned:
  - `action: created-session-from-new-goal; staged-research-problem;`
    `started-literature-harvest; replaced-stale-queue`
  - with a fresh `session_id` and fresh `queue_id`

## GPU Runner Follow-on

The bounded GPU runner is now live in a more useful state than the earlier
placeholder-only path.

Current live behavior on `.44`:

- `gpu-experiment` uses
  `ghcr.io/offensivegeneric/glasslab-gpu-experiment-runner:0.1.4-local`
- `workflow-api` is rolled to `0.1.78-local`
- the runner emits `execution_readiness` instead of the old placeholder
- readiness is broken into explicit components:
  - `target_alignment`
  - `split_contract`
  - `package_stack`
  - `runtime_stack`

Fresh DreamSim-style bounded runs produced:

- direct `!run`
  - `metric_name: execution_readiness`
  - `best_metric: 0.9375`
  - `validation_strategy: stratified_holdout`
  - `validation_split: 0.2`
  - `required_python_packages: ["torch", "timm"]`
  - `available_python_packages: {"torch": true, "timm": true}`
  - `readiness_components`
    - `target_alignment: 1.0`
    - `split_contract: 1.0`
    - `package_stack: 1.0`
    - `runtime_stack: 0.75`
- autoresearch `!launch-iteration`
  - completed on the same runner image
  - `!decide-latest` now upgrades a stale early `escalate_for_review`
    into `keep` once the run has actually completed and scored metrics are
    present
  - `!model-comparison` now shows:
    - `primary_metric_name: execution_readiness`
    - `primary_metric_value: 0.9375`
    - `decision: keep`
    - `recommended_model: vision_transformer`

Meaning:

- the bounded run contract is now genuinely useful for runner-side work
- the image carries the expected Python stack for DreamSim-style technique
  cards
- the autoresearch loop can launch, score, and keep a bounded GPU variant
  without manual repair after the fact
- the next obvious bottleneck is no longer package presence
- it is the quality of the experiment metric itself, since
  `execution_readiness` is still a bounded execution metric rather than a
  real DreamSim replication score
