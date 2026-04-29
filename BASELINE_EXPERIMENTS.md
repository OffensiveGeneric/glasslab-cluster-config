# Baseline Experiments Setup

## Summary

We've successfully created baseline experiments to validate the evaluation pipeline before running full contrastive learning experiments. This addresses the SME's concerns about potential evaluation artifacts causing the observed metrics gap.

## What Was Done

### 1. Created Baseline Experiment Script
**File**: `/Users/glasslab/dml-project/scripts/run_baseline.py`

Supports 4 baseline types:
- **random**: Random Gaussian embeddings (should score ~1% for random chance)
- **frozen_resnet50**: Pretrained ResNet50 without fine-tuning
- **frozen_dino**: Pretrained DINO ViT without fine-tuning  
- **frozen_clip**: Pretrained CLIP without fine-tuning

### 2. Updated Dependencies
- Added `transformers>=4.30.0` to `pyproject.toml`
- Updated Dockerfile to install transformers

### 3. Created Kubernetes Job YAMLs
**Files**:
- `/Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/29-image-prepull.yaml` (updated to cache baseline image)
- `/Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/30-baseline-random.yaml`
- `/Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/31-baseline-resnet50.yaml`
- `/Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/32-baseline-dino.yaml`
- `/Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/33-baseline-clip.yaml`

### 4. Built Docker Image
Image tag: `ghcr.io/offensivegeneric/glasslab-metric-search:baseline-v1`

## How to Run Baselines

On the Kubernetes cluster (using bastion):

```bash
# 1. Apply prepull job to cache images on GPU nodes
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/29-image-prepull.yaml

# 2. Run individual baseline experiments
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/30-baseline-random.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/31-baseline-resnet50.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/32-baseline-dino.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/33-baseline-clip.yaml

# 3. Check job status
kubectl -n glasslab-v2 get jobs
kubectl -n glasslab-v2 get pods -l job-name=baseline-random
kubectl -n glasslab-v2 get pods -l job-name=baseline-resnet50
kubectl -n glasslab-v2 get pods -l job-name=baseline-dino
kubectl -n glasslab-v2 get pods -l job-name=baseline-clip

# 4. View logs
kubectl -n glasslab-v2 logs -f <pod-name>

# 5. View results (metrics will be at /mnt/artifacts/baselines/<baseline-type>/)
```

## Expected Results & Validation

### Random Baseline (Critical Check)
**Expected**: `test_unseen_grouped_recall_at_k ≈ 0.01` (1% for 100 classes)
**If higher**: Evaluation code has bug (leakage, wrong gallery size, etc.)

### Frozen ResNet Baseline
**Expected**: `test_unseen_grouped_recall_at_k ≈ 0.20-0.30`
Shows inherent class separability in CIFAR-100

### Frozen DINO/CLIP Baselines
**Expected**: `test_unseen_grouped_recall_at_k ≈ 0.15-0.25`
Zero-shot foundation model performance

## SME Validation Questions Addressed

1. **Is Grouped Recall@K implemented correctly?**
   - Yes, uses fixed-size groups (K classes per group) to make metric invariant to dataset size
   
2. **Should seen/unseen have same class counts?**
   - Yes, but Grouped Recall@K handles different counts via fixed-size grouping

3. **Are confidence intervals needed?**
   - Yes, but first validate baseline results across multiple seeds

4. **What's the minimum evidence for "unseen generalization"?**
   - DML model must statistically outperform:
     - Random embeddings (~1%)
     - Frozen ImageNet ResNet (~20-30%)
     - Zero-shot CLIP/DINO (~15-25%)

5. **Should we run more eval batches?**
   - Yes, but first verify baselines work with current batch count

## Next Steps

1. **Run baselines** on Kubernetes cluster
2. **Verify random baseline scores ~1%** (critical sanity check)
3. **Compare frozen baselines** to establish performance bounds
4. **If baselines validate**: Run contrastive learning experiments with longer training
5. **If baselines fail**: Debug evaluation pipeline before proceeding

## Files Changed

- **Code**: `/Users/glasslab/dml-project/scripts/run_baseline.py` (new)
- **Config**: `/Users/glasslab/dml-project/pyproject.toml` (added transformers)
- **Docker**: `/Users/glasslab/dml-project/Dockerfile` (added transformers install)
- **K8s Jobs**: 5 YAML files added to cluster-config

## Known Issues

1. Large image size (~15GB) due to transformers + PyTorch dependencies
2. Network speeds slow (~2-7 MB/s) - using prepull job to cache
3. No FAISS on macOS (OpenMP deadlock) - conditional import in metrics.py
