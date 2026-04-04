# Artist Similarity v1

This note turns the current painting-similarity research goal into a bounded
first execution target for Glasslab.

It is intentionally narrower than "solve art attribution."

The first useful target is:

- learn and compare image-space distance metrics for paintings
- using labeled image corpora
- with explicit same-artist vs different-artist evaluation
- while guarding against style drift and split leakage

## Problem Statement

Given a database of labeled paintings, Glasslab should learn an embedding or
distance function that:

- pulls same-label works closer together
- pushes different-label works farther apart
- remains useful when an artist's style changes across their career

This is a deep metric learning problem, not only a closed-set classification
problem.

## First Bounded Objective

The v1 objective is:

- build a bounded image-similarity runner lane
- compare a small set of metric-learning methodologies
- record which methodology is currently best supported

The first supported question should be:

- same artist or different artist?

The first supported downstream artifact should be:

- a ranked methodology comparison for image-similarity approaches on a curated
  art dataset subset

## Candidate Data Sources

The likely first corpus sources are:

- `WikiArt`
- `The Met`

These should not be treated as raw internet sources in the runner path.

They should first be normalized into a bounded dataset contract with fields
like:

- `image_uri`
- `artist_id`
- `artist_name`
- `work_date`
- `medium`
- `movement_or_style`
- `source`
- `split_group`

The first evaluation dataset should likely be derived into:

- pairwise verification examples
- retrieval groups
- hard negatives
- period-separated same-artist pairs

## First Supported Method Families

Based on the current problem statement, the first technique-card-backed
families should be:

1. Contrastive embedding
- pair-based metric learning
- same-label pairs close, different-label pairs apart

2. Triplet embedding
- anchor, positive, negative setup
- requires hard-negative mining discipline

3. Angular-margin baseline
- ArcFace/CosFace style discriminative embedding baseline
- useful as a strong closed-set-to-embedding baseline

4. Classification baseline with embedding reuse
- closed-set classifier
- penultimate-layer embeddings used as similarity vectors

## First Supported Metrics

The first real experiment metric set should move beyond contract quality and
include task metrics such as:

- pairwise ROC-AUC
- pairwise PR-AUC
- same-artist verification accuracy
- retrieval precision@k
- retrieval recall@k
- silhouette score in embedding space

Support metrics worth logging early even if they are not yet decision-critical:

- embedding drift diagnostics
- hubness checks
- split leakage indicators

## First Supported Failure Modes

The first runner path should explicitly track these risks:

- style drift across an artist's career
- leakage from near-duplicate works across train/validation/test
- same-style different-artist confusion
- hard-negative collapse
- embedding hubness
- overfitting under weak validation strategy

## First Bounded Split Policies

The current general split handling is too generic for this problem.

The first artist-similarity lane should support explicit split postures such
as:

- `artist_holdout`
- `period_aware_holdout`
- `stratified_holdout`
- `hard_negative_eval`

For this task, random holdout alone is not good enough.

## How This Fits Glasslab

The near-term execution chain should be:

- manually import one or more artist-similarity technique cards
- create a session goal or manual source for the task
- let interpretation produce a bounded `MethodSpec`
- launch GPU runs through `gpu-experiment`
- compare the first few variants in autoresearch
- persist keep/discard decisions
- synthesize follow-on bounded mutations

The next real milestone is not more architecture.

It is:

- one real image-similarity dataset contract
- one real GPU runner implementation
- one real batch of technique-card-backed comparisons

## Near-Term Non-Goals

Not required for v1:

- broad autonomous literature search
- open-world attribution
- unrestricted code generation
- automatic technique-card authoring
- fully generic multimodal metric learning

The v1 standard is simpler:

- can Glasslab compare a few plausible image-metric methodologies on a real art
  similarity task and tell us which one is winning?
