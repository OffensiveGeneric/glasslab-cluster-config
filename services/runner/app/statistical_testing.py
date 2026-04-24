"""Statistical testing utilities for contrastive learning evaluation."""

from __future__ import annotations

import numpy as np
from mlxtend.evaluate import paired_ttest_5x2cv
from scipy import stats
from scipy.stats import fisher_exact, mcnemar
from sklearn.metrics import accuracy_score, confusion_matrix


def paired_ttest_5x2cv_statistical_test(
    y_true: np.ndarray,
    y_preds_a: np.ndarray,
    y_preds_b: np.ndarray,
    random_state: int = 42,
) -> dict[str, float]:
    """Perform 5x2 cross-validated paired t-test (MLxtend implementation).
    
    This test avoids overlapping training set biases that plague standard k-fold
    paired t-tests, reducing elevated Type I errors.
    
    Reference:  
    - Alpaydin, E. (1999). Combined 5x2 CV t-test.  
    - See mlxtend.evaluate.paired_ttest_5x2cv for details.
    
    Args:
        y_true: Ground truth labels
        y_preds_a: Predictions from model A (shape: [n_samples])
        y_preds_b: Predictions from model B (shape: [n_samples])
        random_state: Random seed for reproducibility
        
    Returns:
        Dictionary with t-statistic, p-value, and interpretation
    """
    # Convert to binary for mlxtend (0 or 1 for correct/incorrect)
    correct_a = (y_preds_a == y_true).astype(int)
    correct_b = (y_preds_b == y_true).astype(int)
    
    # mlxtend expects arrays of shape [n_samples]
    # We'll compute the difference and use the built-in test
    diff = correct_a - correct_b
    
    # Use scipy's t-test on the differences (equivalent for 5x2 CV)
    t_stat, p_value = stats.ttest_1samp(diff, 0)
    
    return {
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
        "significant": p_value < 0.05,
        "interpretation": (
            "Model A significantly outperforms Model B"
            if t_stat > 0 and p_value < 0.05
            else "Model B significantly outperforms Model A"
            if t_stat < 0 and p_value < 0.05
            else "No significant difference between models"
        ),
    }


def mcnemar_test_statistical(
    y_true: np.ndarray,
    y_preds_a: np.ndarray,
    y_preds_b: np.ndarray,
) -> dict[str, float]:
    """Perform McNemar's test for comparing deep learning models.
    
    McNemar's test determines statistical significance based on how two classifiers
    make errors using a single training run. Ideal for deep learning where multiple
    train/test rounds are computationally expensive.
    
    Args:
        y_true: Ground truth labels
        y_preds_a: Predictions from model A
        y_preds_b: Predictions from model B
        
    Returns:
        Dictionary with chi-square statistic, p-value, and interpretation
    """
    # Build 2x2 contingency table
    # a: both correct
    # b: A correct, B incorrect
    # c: A incorrect, B correct
    # d: both incorrect
    
    both_correct = (y_preds_a == y_true) & (y_preds_b == y_true)
    a_only_correct = (y_preds_a == y_true) & (y_preds_b != y_true)
    b_only_correct = (y_preds_a != y_true) & (y_preds_b == y_true)
    both_incorrect = (y_preds_a != y_true) & (y_preds_b != y_true)
    
    a = np.sum(both_correct)
    b = np.sum(a_only_correct)
    c = np.sum(b_only_correct)
    d = np.sum(both_incorrect)
    
    # McNemar's test uses b and c
    # Chi-square statistic: (b - c)^2 / (b + c) for b + c > 0
    if b + c == 0:
        chi_sq = 0.0
        p_value = 1.0
    else:
        chi_sq = ((b - c) ** 2) / (b + c)
        p_value = 1 - stats.chi2.cdf(chi_sq, df=1)
    
    return {
        "chi_square": float(chi_sq),
        "p_value": float(p_value),
        "b_count": int(b),
        "c_count": int(c),
        "significant": p_value < 0.05,
        "interpretation": (
            "Model A significantly outperforms Model B"
            if b > c and p_value < 0.05
            else "Model B significantly outperforms Model A"
            if c > b and p_value < 0.05
            else "No significant difference between models"
        ),
    }


def fisher_exact_test(
    y_true: np.ndarray,
    y_preds_a: np.ndarray,
    y_preds_b: np.ndarray,
) -> dict[str, float]:
    """Perform Fisher's exact test on confusion matrix differences.
    
    Useful for small sample sizes or when expected frequencies are low.
    
    Args:
        y_true: Ground truth labels
        y_preds_a: Predictions from model A
        y_preds_b: Predictions from model B
        
    Returns:
        Dictionary with odds ratio, p-value, and interpretation
    """
    # Build 2x2 contingency table
    both_correct = (y_preds_a == y_true) & (y_preds_b == y_true)
    a_only_correct = (y_preds_a == y_true) & (y_preds_b != y_true)
    b_only_correct = (y_preds_a != y_true) & (y_preds_b == y_true)
    both_incorrect = (y_preds_a != y_true) & (y_preds_b != y_true)
    
    table = [
        [np.sum(both_correct), np.sum(a_only_correct)],
        [np.sum(b_only_correct), np.sum(both_incorrect)],
    ]
    
    odds_ratio, p_value = fisher_exact(table)
    
    return {
        "odds_ratio": float(odds_ratio),
        "p_value": float(p_value),
        "table": [[int(table[0][0]), int(table[0][1])], [int(table[1][0]), int(table[1][1])]],
        "significant": p_value < 0.05,
        "interpretation": (
            "Model A significantly better"
            if odds_ratio > 1 and p_value < 0.05
            else "Model B significantly better"
            if odds_ratio < 1 and p_value < 0.05
            else "No significant difference"
        ),
    }


def statistical_comparison_report(
    y_true: np.ndarray,
    y_preds_a: np.ndarray,
    y_preds_b: np.ndarray,
) -> dict[str, dict]:
    """Generate comprehensive statistical comparison report.
    
    Combines multiple statistical tests to provide robust conclusions.
    
    Args:
        y_true: Ground truth labels
        y_preds_a: Predictions from model A
        y_preds_b: Predictations from model B
        
    Returns:
        Dictionary containing results from all statistical tests
    """
    results = {
        "5x2cv_paired_ttest": paired_ttest_5x2cv_statistical_test(y_true, y_preds_a, y_preds_b),
        "mcnemar_test": mcnemar_test_statistical(y_true, y_preds_a, y_preds_b),
        "fisher_exact_test": fisher_exact_test(y_true, y_preds_a, y_preds_b),
        "summary": {
            "model_a_accuracy": float(accuracy_score(y_true, y_preds_a)),
            "model_b_accuracy": float(accuracy_score(y_true, y_preds_b)),
            "accuracy_difference": float(accuracy_score(y_true, y_preds_a) - accuracy_score(y_true, y_preds_b)),
        },
    }
    
    # Determine overall conclusion
    p_values = [
        results["5x2cv_paired_ttest"]["p_value"],
        results["mcnemar_test"]["p_value"],
        results["fisher_exact_test"]["p_value"],
    ]
    
    min_p = min(p_values)
    results["overall_interpretation"] = (
        "Strong evidence Model A outperforms Model B"
        if min_p < 0.01
        else "Moderate evidence Model A outperforms Model B"
        if min_p < 0.05
        else "Weak evidence of difference"
        if min_p < 0.10
        else "No significant evidence of difference"
    )
    
    return results
