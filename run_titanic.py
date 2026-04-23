#!/usr/bin/env python3
"""Download Titanic competition data without Kaggle API (uses public data)"""

import os
import sys
from pathlib import Path

try:
    import requests
    import zipfile
except ImportError:
    print("Error: requests and zipfile modules required")
    sys.exit(1)

DATASET_DIR = Path("/tmp/titanic-kaggle")
DATASET_DIR.mkdir(parents=True, exist_ok=True)

# Public Kaggle Titanic competition data URLs
TRAIN_URL = "https://raw.githubusercontent.com/ash3h/Titanic-Dataset/main/train.csv"
TEST_URL = "https://raw.githubusercontent.com/ash3h/Titanic-Dataset/main/test.csv"


def download_public_data():
    """Download Titanic data from Kaggle API"""
    import os
    
    print(f"Downloading Titanic data from Kaggle API...")
    
    # Check if data already exists
    train_path = DATASET_DIR / "train.csv"
    test_path = DATASET_DIR / "test.csv"
    
    if train_path.exists() and test_path.exists():
        print("  Using existing downloaded data")
        return True
    
    # Use Kaggle API
    os.environ['KAGGLE_API_TOKEN'] = os.environ.get('KAGGLE_API_TOKEN', '')
    
    import subprocess
    result = subprocess.run(
        ['kaggle', 'competitions', 'download', '-c', 'titanic', '-p', str(DATASET_DIR)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"  Download failed, trying fallback...")
        # Try direct download from public source
        print(f"  Training data...")
        response = requests.get(TRAIN_URL)
        if response.status_code == 200:
            train_path.write_bytes(response.content)
            print(f"    ✓ {len(open(train_path).readlines())-1} rows")
        else:
            print(f"    ✗ Failed to download train.csv: {response.status_code}")
            return False
        
        print(f"  Test data...")
        response = requests.get(TEST_URL)
        if response.status_code == 200:
            test_path.write_bytes(response.content)
            print(f"    ✓ {len(open(test_path).readlines())-1} rows")
        else:
            print(f"    ✗ Failed to download test.csv: {response.status_code}")
            return False
    else:
        # Extract zip
        import zipfile
        zip_path = DATASET_DIR / "titanic.zip"
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(DATASET_DIR)
        os.remove(zip_path)
    
    print(f"\n✓ Data downloaded to: {DATASET_DIR}")
    return True


def run_predictions():
    """Run Titanic predictions on actual Kaggle data"""
    import pandas as pd
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    
    print("\n" + "=" * 60)
    print("Loading Titanic Data")
    print("=" * 60)
    
    train_df = pd.read_csv(DATASET_DIR / "train.csv")
    test_df = pd.read_csv(DATASET_DIR / "test.csv")
    
    print(f"Train data: {len(train_df)} rows")
    print(f"Test data: {len(test_df)} rows")
    
    # Prepare data
    y = train_df['Survived'].astype(int)
    X = train_df.drop(columns=['Survived'])
    
    # Split for validation
    X_train, X_valid, y_train, y_valid = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    
    print(f"Train split: {len(X_train)} rows")
    print(f"Valid split: {len(X_valid)} rows")
    
    # Define columns
    numeric_cols = ['Age', 'SibSp', 'Parch', 'Fare']
    categorical_cols = ['Pclass', 'Sex', 'Embarked']
    
    # Create preprocessor
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_cols),
            ('cat', categorical_transformer, categorical_cols)
        ]
    )
    
    # Build pipeline
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('model', RandomForestClassifier(n_estimators=300, random_state=42, min_samples_leaf=1))
    ])
    
    # Train and validate
    print("\n[1] Training Random Forest model...")
    pipeline.fit(X_train, y_train)
    
    predictions_valid = pipeline.predict(X_valid)
    accuracy = accuracy_score(y_valid, predictions_valid)
    print(f"✓ Validation accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
    
    # Train on full data
    print("\n[2] Retraining on full training set...")
    pipeline.fit(X, y)
    
    # Predict on test set
    print("\n[3] Making predictions on Kaggle test set...")
    predictions_test = pipeline.predict(test_df[X.columns])
    
    # Create submission
    submission = pd.DataFrame({
        'PassengerId': test_df['PassengerId'].astype(int),
        'Survived': predictions_test.astype(int)
    })
    
    # Save submission
    submission_path = DATASET_DIR / "submission.csv"
    submission.to_csv(submission_path, index=False)
    
    print(f"\n✓ Submission saved: {submission_path}")
    print(f"  Shape: {submission.shape}")
    print(f"  Survived: {submission['Survived'].sum()}")
    print(f"  Survival rate: {submission['Survived'].mean()*100:.1f}%")
    
    # Show statistics
    print("\n" + "=" * 60)
    print("Submission Summary")
    print("=" * 60)
    print(f"Total predictions: {len(submission)}")
    print(f"Survived: {submission['Survived'].sum()}")
    print(f"Did not survive: {(submission['Survived'] == 0).sum()}")
    
    # Show sample predictions
    print("\nSample predictions (first 10):")
    print(submission.head(10).to_string(index=False))
    
    return submission


def main():
    """Main workflow"""
    print("=" * 60)
    print("Glasslab v2 - Kaggle Titanic Competition")
    print("=" * 60)
    
    # Download data
    print("\n[1] Downloading Titanic data...")
    if not download_public_data():
        print("Failed to download data")
        return False
    
    # Run predictions
    print("\n[2] Running predictions...")
    submission = run_predictions()
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
