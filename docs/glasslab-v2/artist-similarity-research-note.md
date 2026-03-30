# Artist Similarity Research Note

This note captures the research direction Grossberg articulated for Glasslab.

## Core problem

The task is not just:

- classify a painting by artist

The more important task is:

- given two paintings, determine whether they are by the same artist

That means the system should be able to learn or derive a distance measure over artworks, not only a closed-set label predictor.

## Why this matters

A plain artist-classification model is too narrow for the actual research question.

We want a system that can handle cases like:

- two paintings by the same artist but from different periods
- significant style drift across an artist's career
- visually similar works by different artists
- partial or ambiguous evidence

So the target is not only accuracy on artist labels. The target is a robust notion of artistic similarity that can support:

- same-artist vs different-artist decisions
- ranking or retrieval of stylistically related works
- comparison of multiple candidate methodologies for this question

## Desired research capability

Glasslab should support bounded methodology exploration for questions like:

- what distance metric best captures artist identity across style drift?
- which representation works best for pairwise artist comparison?
- which evaluation setup most accurately reflects real attribution ambiguity?

In other words, the system should be able to compare multiple approaches to the same research problem rather than locking onto one classifier architecture too early.

## First-pass methodological space

The first bounded methodology set for this question should include multiple families of approaches:

### 1. Embedding + distance approaches

- CNN or ViT feature extractor
- metric learning / contrastive learning
- triplet-loss or Siamese-style setups
- cosine, Euclidean, or learned similarity heads

This is the most direct route to the "same artist / different artist" framing.

### 2. Closed-set artist classification baselines

- standard artist classifier
- compare penultimate-layer embeddings as a downstream similarity signal

These are useful baselines even if they are not the final answer.

### 3. Retrieval-oriented approaches

- nearest-neighbor search in embedding space
- prototype or centroid approaches per artist
- temporal or period-aware artist prototypes

These may help with within-artist variation across a career.

### 4. Style-aware / drift-aware approaches

- cluster by career phase or period before comparison
- compare local composition, brushwork, palette, and texture signals
- combine global embedding similarity with period/style subspace similarity

This is important because "same artist" may not look like a single compact cluster.

## Dataset and evaluation implications

The evaluation should not be limited to closed-set top-1 artist accuracy.

We should explicitly support metrics and tasks such as:

- same-artist / different-artist verification accuracy
- ROC-AUC or PR-AUC for pairwise similarity
- retrieval precision at k
- hard-negative evaluation against artists with similar style
- robustness across time-separated works from the same artist

The data split design matters a lot.

Good splits should test:

- artist holdout behavior when possible
- temporal split or period-aware split within artist
- hard negative pairs
- pairwise evaluation, not only class labels

## What Glasslab should do with this

This research problem fits the bounded autoresearch lane well.

The system should:

1. gather literature on artist attribution, visual similarity, metric learning, and style analysis
2. interpret the literature into candidate methodology families
3. draft a small set of bounded methodology variants
4. map each variant onto an approved execution template such as `gpu-experiment`
5. run short validation comparisons
6. compare model families and distance formulations
7. persist keep/discard/review decisions with evidence

That is a much better fit than asking OpenClaw to simply "pick a model."

## Key requirement for the platform

Grossberg's priority can be stated more precisely as:

Glasslab should be able to decide which model or representation family is best for a research question by running bounded comparisons and persisting the evidence behind the choice.

For this painting problem, that specifically means:

- compare multiple representation and similarity strategies
- compare multiple distance measures
- compare their robustness to style drift
- record which methodology is currently best supported by the evidence

## What is out of scope for the first pass

The first pass does not need to solve:

- general unconstrained art-historical reasoning
- open-world authorship attribution across arbitrary corpora
- automatic crawling behind restricted museum or journal access
- unrestricted model or code mutation

The first useful bounded target is:

- a reviewable research loop that can compare several plausible methodologies for same-artist vs different-artist painting comparison and track which one is winning
