#!/usr/bin/env python3
"""
FAISS Integration Test Submission Script

Submits a FAISS integration test job to the Kubernetes cluster.
"""

import json
import sys
import subprocess
from pathlib import Path

def submit_faiss_test():
    """Submit FAISS integration test job"""
    
    # The job definition file
    job_file = Path("/Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/11-faiss-integration-test.yaml")
    
    if not job_file.exists():
        print(f"✗ Job file not found: {job_file}")
        return None
    
    print("=" * 60)
    print("FAISS Integration Test - Job Submission")
    print("=" * 60)
    print()
    
    print(f"Job definition: {job_file}")
    print()
    
    # Apply the job definition
    print("Submitting job to Kubernetes...")
    result = subprocess.run(
        ["kubectl", "apply", "-f", str(job_file)],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✓ Job submitted successfully!")
        print()
        print("Output:")
        print(result.stdout)
        
        # Try to get job info
        try:
            job_info = subprocess.run(
                ["kubectl", "-n", "glasslab-v2", "get", "jobs", "faiss-integration-test", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if job_info.returncode == 0:
                job_data = json.loads(job_info.stdout)
                print()
                print("Job Details:")
                print(f"  Name: {job_data['metadata']['name']}")
                print(f"  Namespace: {job_data['metadata']['namespace']}")
        except Exception as e:
            print(f"  Could not retrieve job details: {e}")
        
        return {"status": "submitted"}
    else:
        print("✗ Failed to submit job")
        print(f"  Error: {result.stderr}")
        return None

if __name__ == "__main__":
    result = submit_faiss_test()
    
    if result:
        print()
        print("=" * 60)
        print("Job submitted to Kubernetes")
        print()
        print("To monitor the job, run:")
        print("  kubectl -n glasslab-v2 get pods -l job-name=faiss-integration-test")
        print("  kubectl -n glasslab-v2 logs -f -l job-name=faiss-integration-test")
        print("  kubectl -n glasslab-v2 describe job faiss-integration-test")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("=" * 60)
        print("Failed to submit job")
        print("=" * 60)
        sys.exit(1)
