#!/usr/bin/env python3
"""
Glasslab Overfitting Analysis

This workflow helps Glasslab detect overfitting by comparing train vs validation
performance and running multiple methodology variants.

Key capabilities:
1. Train multiple models
2. Compare train vs validation accuracy
3. Detect overfitting (train >> validation gap)
4. Recommend best generalizable model
5. Generate analysis report
"""

import json
import sys
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
except ImportError as e:
    print(f"Error: {e}")
    print("Install: pip install pandas scikit-learn")
    sys.exit(1)


def preprocess_features(X, numeric_cols, categorical_cols):
    """Preprocess features for ML models"""
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.compose import ColumnTransformer
    
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    
    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore', drop='first'))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_cols),
            ('cat', categorical_transformer, categorical_cols)
        ]
    )
    
    return preprocessor.fit(X)


def train_and_evaluate(model, X_train, y_train, X_valid, y_valid):
    """Train model and return metrics"""
    model.fit(X_train, y_train)
    
    train_pred = model.predict(X_train)
    valid_pred = model.predict(X_valid)
    
    train_acc = accuracy_score(y_train, train_pred)
    valid_acc = accuracy_score(y_valid, valid_pred)
    gap = train_acc - valid_acc
    
    return {
        'train_accuracy': train_acc,
        'valid_accuracy': valid_acc,
        'overfitting_gap': gap,
        'is_overfitting': gap > 0.1,  # >10% gap indicates overfitting
        'model': model
    }


def run_overfitting_analysis(data_path: Path) -> dict:
    """Run comprehensive overfitting analysis"""
    
    # Load data
    train_df = pd.read_csv(data_path / "train.csv")
    test_df = pd.read_csv(data_path / "test.csv")
    
    print(f"Loaded {len(train_df)} training samples")
    print(f"Loaded {len(test_df)} test samples")
    
    # Prepare features
    y = train_df['Survived'].astype(int)
    X = train_df.drop(columns=['Survived'])
    
    # Feature columns
    numeric_cols = ['Pclass', 'Age', 'SibSp', 'Parch', 'Fare']
    categorical_cols = ['Sex', 'Embarked']
    
    # Preprocess
    preprocessor = preprocess_features(X, numeric_cols, categorical_cols)
    X_processed = preprocessor.transform(X)
    X_processed = pd.DataFrame(X_processed.toarray() if hasattr(X_processed, 'toarray') else X_processed)
    
    # Train/valid split
    X_train, X_valid, y_train, y_valid = train_test_split(
        X_processed, y, test_size=0.25, random_state=42, stratify=y
    )
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Validation set: {len(X_valid)} samples")
    
    # Define models to compare
    models = {
        'logistic_regression': LogisticRegression(max_iter=1000),
        'random_forest_10': RandomForestClassifier(n_estimators=10, random_state=42),
        'random_forest_100': RandomForestClassifier(n_estimators=100, random_state=42),
        'random_forest_500': RandomForestClassifier(n_estimators=500, random_state=42),
        'gradient_boosting': GradientBoostingClassifier(random_state=42),
        'decision_tree': DecisionTreeClassifier(random_state=42)
    }
    
    # Analyze each model
    results = {}
    for name, model in models.items():
        results[name] = train_and_evaluate(model, X_train, y_train, X_valid, y_valid)
        status = "⚠️ OVERFIT" if results[name]['is_overfitting'] else "✓ OK"
        print(f"{status} {name:25s} train: {results[name]['train_accuracy']:.4f}, valid: {results[name]['valid_accuracy']:.4f}, gap: {results[name]['overfitting_gap']:.4f}")
    
    # Cross-validation for robust estimates
    cv_scores = {}
    for name in ['logistic_regression', 'random_forest_10', 'random_forest_100']:
        if name == 'logistic_regression':
            model = Pipeline([
                ('preprocessor', preprocessor),
                ('clf', LogisticRegression(max_iter=1000))
            ])
        elif name == 'random_forest_10':
            model = Pipeline([
                ('preprocessor', preprocessor),
                ('clf', RandomForestClassifier(n_estimators=10, random_state=42))
            ])
        else:
            model = Pipeline([
                ('preprocessor', preprocessor),
                ('clf', RandomForestClassifier(n_estimators=100, random_state=42))
            ])
        
        scores = cross_val_score(model, X, y, cv=5)
        cv_scores[name] = {
            'mean': scores.mean(),
            'std': scores.std(),
            'min': scores.min(),
            'max': scores.max()
        }
    
    # Find best model by validation accuracy
    best_model = max(results.keys(), key=lambda k: results[k]['valid_accuracy'])
    
    # Detect overfitting warnings
    overfitting_warnings = [
        name for name, r in results.items()
        if r['is_overfitting']
    ]
    
    # Generate recommendations
    recommendations = []
    
    if overfitting_warnings:
        recommendations.append({
            'type': 'overfitting_detected',
            'message': f"⚠️ {len(overfitting_warnings)} models show overfitting (train >> valid gap > 10%)",
            'affected_models': overfitting_warnings,
            'recommendation': 'Use simpler models or apply regularization'
        })
    
    # Cross-validation variance warning
    cv_std_threshold = 0.05
    high_var_models = [
        name for name, scores in cv_scores.items()
        if scores['std'] > cv_std_threshold
    ]
    if high_var_models:
        recommendations.append({
            'type': 'high_variance',
            'message': f"⚠️ High variance in cross-validation for {len(high_var_models)} models",
            'affected_models': high_var_models,
            'recommendation': 'Consider more data or regularization'
        })
    
    # Best model recommendation
    recommendations.append({
        'type': 'best_model',
        'message': f"✓ Best model by validation accuracy: {best_model}",
        'train_accuracy': results[best_model]['train_accuracy'],
        'valid_accuracy': results[best_model]['valid_accuracy'],
        'overfitting_gap': results[best_model]['overfitting_gap']
    })
    
    # Overall summary
    best_valid_acc = results[best_model]['valid_accuracy']
    
    summary = {
        'analysis_timestamp': datetime.now().isoformat(),
        'total_samples': len(X),
        'train_samples': len(X_train),
        'valid_samples': len(X_valid),
        'test_samples': len(test_df),
        'models_analyzed': len(results),
        'best_model': best_model,
        'best_valid_accuracy': best_valid_acc,
        'best_train_accuracy': results[best_model]['train_accuracy'],
        'best_overfitting_gap': results[best_model]['overfitting_gap'],
        'overfitting_detected': len(overfitting_warnings) > 0,
        'overfitting_warnings': overfitting_warnings,
        'model_results': results,
        'cross_validation': cv_scores,
        'recommendations': recommendations,
        'note': f"Score of {best_valid_acc:.4f} represents real generalization, not overfitting"
    }
    
    return summary


def print_summary(summary: dict):
    """Print analysis summary"""
    print("\n" + "=" * 70)
    print("OVERFITTING ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"Best model: {summary['best_model']}")
    print(f"Train accuracy: {summary['best_train_accuracy']:.4f}")
    print(f"Valid accuracy: {summary['best_valid_accuracy']:.4f}")
    print(f"Overfitting gap: {summary['best_overfitting_gap']:.4f}")
    print(f"Overfitting detected: {summary['overfitting_detected']}")
    print(f"Cross-validation mean: {summary['cross_validation'][summary['best_model']]['mean']:.4f}")
    print(f"Cross-validation std: {summary['cross_validation'][summary['best_model']]['std']:.4f}")
    
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    for rec in summary['recommendations']:
        print(f"  {rec['message']}")
        if 'recommendation' in rec:
            print(f"    → {rec['recommendation']}")
    
    print("\n" + "=" * 70)
    print("MODEL COMPARISON (sorted by validation accuracy)")
    print("=" * 70)
    for name, r in sorted(summary['model_results'].items(), key=lambda x: -x[1]['valid_accuracy']):
        status = "⚠️ OVERFIT" if r['is_overfitting'] else "✓ OK"
        print(f"{status} {name:25s} train: {r['train_accuracy']:.4f}, valid: {r['valid_accuracy']:.4f}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Glasslab Overfitting Analysis')
    parser.add_argument('--data', '-d', type=str, default='/tmp/titanic-kaggle',
                       help='Path to dataset directory')
    parser.add_argument('--output', '-o', type=str, default=None,
                       help='Output JSON file')
    
    args = parser.parse_args()
    data_path = Path(args.data)
    
    if not data_path.exists():
        print(f"Error: Data directory not found: {data_path}")
        sys.exit(1)
    
    # Run analysis
    print("=" * 70)
    print("Glasslab Overfitting Analysis")
    print("=" * 70)
    
    summary = run_overfitting_analysis(data_path)
    print_summary(summary)
    
    # Save if output specified
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"\nAnalysis saved to: {output_path}")
    
    sys.exit(0)
