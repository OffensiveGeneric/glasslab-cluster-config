#!/usr/bin/env python3
"""Operator tool: poll a Kubernetes Job and dump logs on terminal status.

Used from a contributor workstation to manually observe a FAISS integration
test job. kubectl errors are silently folded into return-code checks — a job
that never appears (or disappears mid-poll) returns None. The poll interval
advances by a fixed increment, not wall-clock time, so the printed elapsed
seconds drift proportionally to kubectl latency.
"""

import json
import sys
import subprocess
import time
from pathlib import Path

def run_kubectl(args, namespace="glasslab-v2"):
    """Run kubectl command and return result"""
    cmd = ["kubectl", "-n", namespace] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result
    except subprocess.TimeoutExpired:
        # Returncode 124 is the POSIX timeout convention; callers only
        # inspect returncode, so the failure mode is intentionally uniform.
        return subprocess.CompletedProcess(cmd, 124, "", "Timeout")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

def get_job_status(job_name="faiss-integration-test"):
    """Get the status of the FAISS test job"""
    result = run_kubectl(["get", "job", job_name, "-o", "json"])
    if result.returncode == 0:
        return json.loads(result.stdout)
    return None

def get_pod_status(job_name="faiss-integration-test"):
    """Get pod status for the job"""
    result = run_kubectl(["get", "pods", "-l", f"job-name={job_name}", "-o", "json"])
    if result.returncode == 0:
        return json.loads(result.stdout)
    return None

def get_job_logs(job_name="faiss-integration-test"):
    """Get logs for the job's pod"""
    # Get pod name first
    result = run_kubectl(["get", "pods", "-l", f"job-name={job_name}", "-o", "jsonpath='{.items[0].metadata.name}'"])
    if result.returncode != 0 or not result.stdout.strip():
        print("No pod found for job")
        return None
    
    # kubectl jsonpath wraps the pod name in single quotes; strip them
    # before passing to the logs subcommand.
    pod_name = result.stdout.strip().strip("'")
    print(f"Getting logs for pod: {pod_name}")
    
    result = run_kubectl(["logs", pod_name])
    if result.returncode == 0:
        return result.stdout
    return None

def monitor_job(max_wait_seconds=600, poll_interval=10):
    """Monitor job progress until completion"""
    print("Monitoring FAISS Integration Test Job")
    print("=" * 60)
    print()
    
    elapsed = 0
    while elapsed < max_wait_seconds:
        job = get_job_status()
        
        if job is None:
            print("Job not found. Has it been submitted?")
            # Hardcoded path targets the submit-faiss-test.py counterpart on
            # the same workstation; this is not a general-purpose path.
            print("Run: kubectl apply -f /Users/glasslab/cluster-config/kubeadm/glasslab-v2/jobs/11-faiss-integration-test.yaml")
            return None
        
        status = job.get('status', {})
        conditions = status.get('conditions', [])
        
        active = status.get('active', 0)
        succeeded = status.get('succeeded', 0)
        failed = status.get('failed', 0)
        
        print(f"[{elapsed}s] Active: {active}, Succeeded: {succeeded}, Failed: {failed}")
        
        if conditions:
            for condition in conditions:
                condition_type = condition.get('type', 'unknown')
                status_val = condition.get('status', 'unknown')
                reason = condition.get('reason', '')
                message = condition.get('message', '')
                print(f"  Condition: {condition_type} = {status_val}")
                if reason:
                    print(f"  Reason: {reason}")
                if message:
                    print(f"  Message: {message}")
        
        if succeeded > 0:
            print()
            print("=" * 60)
            print("✓ Job completed successfully!")
            print("=" * 60)
            
            # Get logs
            logs = get_job_logs()
            if logs:
                print()
                print("Job Logs:")
                print("-" * 60)
                print(logs)
                print("-" * 60)
            
            return job
        
        if failed > 0:
            print()
            print("=" * 60)
            print("✗ Job failed")
            print("=" * 60)
            
            # Get logs
            logs = get_job_logs()
            if logs:
                print()
                print("Job Logs:")
                print("-" * 60)
                print(logs)
                print("-" * 60)
            
            return job
        
        time.sleep(poll_interval)
        # Sleep-then-add approximates elapsed time. Actual wall-clock time
        # is longer when kubectl calls are slow, so the printed value
        # under-reports rather than over-reports.
        elapsed += poll_interval
    
    print()
    print("=" * 60)
    print("✗ Timeout waiting for job completion")
    print("=" * 60)
    return None

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("Usage: python monitor-faiss-test.py [job-name]")
        print()
        print("Example:")
        print("  python monitor-faiss-test.py")
        print("  python monitor-faiss-test.py my-faiss-test")
        print()
        print("Monitors the FAISS integration test job until completion.")
        sys.exit(0)
    
    job_name = sys.argv[1] if len(sys.argv) > 1 else "faiss-integration-test"
    
    print("=" * 60)
    print("FAISS Integration Test Monitor")
    print("=" * 60)
    print()
    
    run = monitor_job()
    
    if run:
        print()
        print("Job completed. Use these commands for more details:")
        print("  kubectl -n glasslab-v2 describe job faiss-integration-test")
        print("  kubectl -n glasslab-v2 get pods -l job-name=faiss-integration-test")
        print("  kubectl -n glasslab-v2 delete job faiss-integration-test")
        sys.exit(0)
    else:
        sys.exit(1)
