#!/bin/bash
# Script to run baseline experiments on Kubernetes cluster

set -e

echo "=== Running Baseline Experiments ==="
echo "Date: $(date)"
echo ""

# Apply prepull job to cache images
echo "Applying prepull job..."
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/29-image-prepull.yaml

# Wait for prepull to complete
echo "Waiting for prepull job..."
kubectl wait --for=condition=complete job/prepull-glasslab-metric-search -n glasslab-v2 --timeout=5m

# Apply baseline jobs
echo "Applying baseline jobs..."
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/30-baseline-random.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/31-baseline-resnet50.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/32-baseline-dino.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/33-baseline-clip.yaml

# Apply 64GB baseline jobs
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/34-baseline-random-64gb.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/35-baseline-resnet50-64gb.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/36-baseline-dino-64gb.yaml
kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/37-baseline-clip-64gb.yaml

# Monitor jobs
echo ""
echo "=== Monitoring Jobs ==="
echo "Check progress with:"
echo "  kubectl -n glasslab-v2 get pods -l baseline-type"
echo "  kubectl -n glasslab-v2 logs -f <pod-name>"
echo ""
echo "View results after completion:"
echo "  kubectl cp <pod-name>:/mnt/artifacts/baselines /tmp/baselines"
echo ""
