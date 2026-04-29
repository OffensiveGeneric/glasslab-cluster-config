# Baseline Experiments: 64GB Mac (.23) Setup

## Node Resources

**Node .23 (CS60138N73111)** - Primary 64GB Mac:
- RAM: ~64 GiB allocatable
- GPU: 1 NVIDIA GPU
- Hostname: `CS60138N73111`

**Node .19 (CS60137N7311)** - Secondary Mac:
- RAM: ~32 GiB allocatable  
- GPU: 1 NVIDIA GPU
- Hostname: `CS60137N7311`

**Current cluster nodes:**
- node01: ~64 GiB, 1 GPU (likely .23)
- node02: ~64 GiB, 1 GPU
- node04: ~32 GiB, 1 GPU (likely .19)

## Memory Constraints

**Previous failure:** `max_eval_batches=8` OOMKilled with 32Gi limit
- Pod hit container memory limit, exited with code 137
- Nodes weren't out of memory; container limit was too low

**Solution for 64GB nodes:**
- Request: 48Gi memory
- Limit: 56Gi memory
- Node affinity: node01, node02 only (exclude node04 with 32Gi)

## Updated Baseline Jobs

Created 4 new jobs targeting 64GB nodes:

| Job | File | Description |
|-----|------|-------------|
| baseline-random-64gb | `34-baseline-random-64gb.yaml` | Random embeddings baseline |
| baseline-resnet50-64gb | `35-baseline-resnet50-64gb.yaml` | Frozen ResNet50 baseline |
| baseline-dino-64gb | `36-baseline-dino-64gb.yaml` | Frozen DINO ViT baseline |
| baseline-clip-64gb | `37-baseline-clip-64gb.yaml` | Frozen CLIP baseline |

**Key changes:**
- `requests.memory: 48Gi` (ensures scheduling on 64GB nodes only)
- `limits.memory: 56Gi` (allows using most of node memory)
- `nodeAffinity` excludes node04 (32GB node)
- `max_eval_batches=20` (reduced from 50 for safer memory usage)

## SQLite Streaming

All baseline jobs use SQLite to stream embeddings to disk:

```yaml
--db-type=sqlite
--db-path=/mnt/artifacts/baselines/<baseline>/embeddings.db
```

**How it works:**
1. Embeddings computed batch-by-batch
2. Each batch stored in SQLite database on PVC
3. Memory freed after each batch (no embedding accumulation)
4. Metrics computed by reading from SQLite in chunks

**Database tables:**
- `random_embeddings(split_name, batch_idx, embeddings, labels)`
- `resnet50_embeddings(split_name, batch_idx, embeddings, labels)`
- `dino_embeddings(split_name, batch_idx, embeddings, labels)`
- `clip_embeddings(split_name, batch_idx, embeddings, labels)`

## Running on .23

```bash
# 1. Copy baseline image to .23
# On .23:
cd ~/dml-project
git pull origin main

# 2. Run baseline experiments
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/34-baseline-random-64gb.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/35-baseline-resnet50-64gb.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/36-baseline-dino-64gb.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/37-baseline-clip-64gb.yaml

# 3. Monitor progress
kubectl -n glasslab-v2 get pods -l baseline-type=random
kubectl -n glasslab-v2 logs -f <pod-name>

# 4. Check results (on .23)
ls /Users/glasslab/dml-project/baselines/random
ls /Users/glasslab/dml-project/baselines/resnet50
ls /Users/glasslab/dml-project/baselines/dino
ls /Users/glasslab/dml-project/baselines/clip
```

## Expected Results

| Baseline | Expected `test_unseen_grouped_recall_at_k` |
|----------|--------------------------------------------|
| random | ~0.01 (1% chance for 100 classes) |
| resnet50 | ~0.20-0.30 |
| dino | ~0.15-0.25 |
| clip | ~0.15-0.25 |

**Critical sanity check:** Random baseline MUST score ~1%. If significantly higher, evaluation pipeline has bug (leakage, wrong gallery size, etc.)

## Memory Safety

The baseline script implements several memory-safe patterns:

1. **SQLite streaming:** Embeddings written to disk, not kept in RAM
2. **GPU memory cleanup:** `torch.cuda.empty_cache()` after each batch
3. **Chunked metrics:** Metrics computed on SQLite data in chunks
4. **Node isolation:** Jobs scheduled only on 64GB nodes via affinity

## Results Tracking

Results saved to:
- Metrics JSON: `/mnt/artifacts/baselines/<baseline>/<baseline>_metrics.json`
- Report Markdown: `/mnt/artifacts/baselines/<baseline>/<baseline>_report.md`

Example output format:
```json
{
  "test_unseen_grouped_recall_at_k": 0.234,
  "test_unseen_composite_score": 0.345,
  "generalization_gap_grouped_recall_at_k": -0.123,
  "baseline": "random",
  "mode": "baseline",
  "simulated": false
}
```

## Next Steps After Baselines

1. Verify random baseline scores ~1%
2. Compare frozen baselines for performance bounds
3. If validated: Run full contrastive learning experiments
4. If failed: Debug evaluation pipeline before proceeding
