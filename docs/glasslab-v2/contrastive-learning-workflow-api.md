# Contrastive Learning Workflow API

## Overview

This document describes the workflow-api endpoints for contrastive learning experiments.

## Endpoints

### POST /runs

Create a new contrastive learning experiment run.

**Request:**

```json
{
  "experiment_id": "contrastive-cifar100-001",
  "runner_image": "glasslab/runner:gpu-v1",
  "config": "configs/search_spaces/cifar100_contrastive_v0.yaml",
  "dataset": "cifar100",
  "seen_classes": 80,
  "unseen_classes": 20,
  "seeds": [3, 5],
  "metrics": ["grouped_recall_at_k", "opis", "ami", "ari", "nmi", "silhouette"]
}
```

**Response:**

```json
{
  "run_id": "run_abc123",
  "experiment_id": "contrastive-cifar100-001",
  "status": "pending",
  "created_at": "2026-04-24T12:00:00Z"
}
```

### GET /runs/{run_id}

Get status of a specific run.

### GET /runs

List all runs.

## Contrastive Learning Config

```yaml
# configs/search_spaces/cifar100_contrastive_v0.yaml
experiment:
  name: cifar100-contrastive-v0
  dataset: cifar100
  split:
    seen_classes: 80
    unseen_classes: 80
    total_classes: 100
  seeds: [3, 5]

model:
  backbone: ResNet-101
  embedding_dim: 512
  temperature: 0.07
  projection_dim: 128

loss:
  type: contrastive
  methods:
    - name: shadow_loss
      params:
        temperature: 0.07
        base_temperature: 0.07
    - name: l2a_nc
      params:
        synthetic_ratio: 0.2
        margin: 1.0

augmentation:
  random_resized_crop:
    size: 32
    scale: [0.2, 1.0]
    ratio: [0.75, 1.333]
  color_jitter:
    brightness: 0.8
    contrast: 0.8
    saturation: 0.8
    hue: 0.2
  random_horizontal_flip: true

training:
  epochs: 100
  batch_size: 128
  learning_rate: 0.001
  optimizer: adam
  scheduler: cosine

metrics:
  grouped_recall_at_k:
    k_values: [1, 5, 10, 20, 50]
  opis:
    num_thresholds: 100
  ami: true
  ari: true
  nmi: true
  silhouette: true
```

## Validation

After submitting a run, monitor via:

```bash
# Check run status
curl -s http://workflow-api:8000/runs/contrastive-cifar100-001 | jq .

# Check logs
kubectl logs -n glasslab-v2 <runner-pod> -f

# Check metrics in MinIO
# Path: glasslab-artifacts/contrastive-cifar100-001/metrics/
```

## Error Handling

Common errors:

1. **No GPU available**: Wait for node02 to become available
2. **Image pull error**: Ensure `glasslab/runner:gpu-v1` is accessible
3. **Config parse error**: Validate YAML syntax
4. **Dataset not found**: Upload CIFAR-100 to MinIO first

## Example Script

```bash
#!/usr/bin/env bash

# Submit contrastive learning experiment
curl -X POST http://workflow-api:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "experiment_id": "contrastive-cifar100-001",
    "runner_image": "glasslab/runner:gpu-v1",
    "config": "configs/search_spaces/cifar100_contrastive_v0.yaml",
    "dataset": "cifar100",
    "seen_classes": 80,
    "unseen_classes": 20,
    "seeds": [3, 5],
    "metrics": ["grouped_recall_at_k", "opis", "ami", "ari", "nmi", "silhouette"]
  }' | jq .

# Monitor
while true; do
  curl -s http://workflow-api:8000/runs/contrastive-cifar100-001 | jq '.status'
  sleep 10
done
```
