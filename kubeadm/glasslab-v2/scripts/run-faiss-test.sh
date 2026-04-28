#!/bin/bash
# Submit FAISS Integration Test to Kubernetes Cluster

set -e

echo "============================================================"
echo "FAISS Integration Test - Job Submission"
echo "============================================================"
echo ""

# Navigate to cluster config
cd /Users/glasslab/cluster-config

# Apply the job definition
echo "Applying FAISS integration test job..."
kubectl apply -f kubeadm/glasslab-v2/jobs/11-faiss-integration-test.yaml

echo ""
echo "Job submitted successfully!"
echo ""
echo "To monitor the job, run:"
echo "  kubectl -n glasslab-v2 get pods -l job-name=faiss-integration-test"
echo "  kubectl -n glasslab-v2 get jobs faiss-integration-test"
echo "  kubectl -n glasslab-v2 logs -l job-name=faiss-integration-test"
echo ""
echo "To view logs in real-time:"
echo "  kubectl -n glasslab-v2 logs -f -l job-name=faiss-integration-test"
echo ""
echo "To check job status:"
echo "  kubectl -n glasslab-v2 describe job faiss-integration-test"
echo ""