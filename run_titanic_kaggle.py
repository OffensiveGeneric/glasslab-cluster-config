#!/usr/bin/env python3
"""Run Kaggle Titanic competition predictions"""

import os
import sys
import json
from pathlib import Path

# Add cluster-config to path
CLUSTER_CONFIG = Path(__file__).parent / "cluster-config"
sys.path.insert(0, str(CLUSTER_CONFIG / "services" / "runner"))

def run_with_fixtures():
    """Run with existing test fixtures"""
    import pandas as pd
    from app.config import Settings
    from app.runner import run_experiment, write_supporting_artifacts
    
    FIXTURES_DIR = CLUSTER_CONFIG / "services" / "runner" / "tests" / "fixtures" / "titanic"
    
    train_df = pd.read_csv(FIXTURES_DIR / "train.csv")
    test_df = pd.read_csv(FIXTURES_DIR / "test.csv")
    
    print(f"Train data: {len(train_df)} rows")
    print(f"Test data: {len(test_df)} rows (fixtures)")
    
    # Run with runner
    os.environ['GLASSLAB_RUNNER_DATASET_ROOT'] = str(FIXTURES_DIR)
    os.environ['GLASSLAB_RUNNER_ARTIFACTS_ROOT'] = '/tmp/glasslab-artifacts'
    os.environ['GLASSLAB_RUNNER_SPEC_JSON'] = json.dumps({
        "pipeline": "titanic_baseline",
        "dataset": "titanic",
        "models": ["logistic_regression", "random_forest"],
        "feature_profile": "basic",
        "resource_profile": "cpu-small",
        "compare_to": "none",
        "produce_submission": True
    })
    
    settings = Settings()
    result = run_experiment(settings)
    write_supporting_artifacts(settings, result, status='succeeded')
    
    print(f"\nRunner completed!")
    print(f"Best model: {result['best_model']}")
    print(f"Best metric: {result['best_metric']}")
    
    submission = pd.read_csv(result['submission_path'])
    print(f"Submission shape: {submission.shape}")
    
    return submission


def main():
    print("=" * 60)
    print("Glasslab v2 - Kaggle Titanic Competition")
    print("=" * 60)
    
    print("\n[Using test fixtures]")
    submission = run_with_fixtures()
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
