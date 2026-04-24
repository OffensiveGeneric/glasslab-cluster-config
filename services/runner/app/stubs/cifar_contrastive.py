# Stub for src.metrics.cifar_contrastive
# This is needed for contrastive_runner.py but the actual implementation
# will be provided by the cluster runtime

import numpy as np
from typing import Dict, Any


def grouped_recall_at_k(
    embeddings: np.ndarray,
    labels: np.ndarray,
    k: int = 10,
    n_groups: int = 4
) -> float:
    """Compute grouped recall at K."""
    n_samples = len(labels)
    if n_samples == 0:
        return 0.0
    
    recall_scores = []
    for i in range(n_samples):
        anchor_label = labels[i]
        distances = np.linalg.norm(embeddings - embeddings[i], axis=1)
        indices = np.argsort(distances)[1:k+1]
        matching = sum(1 for idx in indices if labels[idx] == anchor_label)
        recall_scores.append(matching / min(k, n_samples - 1))
    
    return np.mean(recall_scores)


def compute_opis(
    embeddings: np.ndarray,
    labels: np.ndarray,
    threshold_range=None
) -> float:
    """Compute Operating-Point-Inconsistency Score."""
    if threshold_range is None:
        threshold_range = np.linspace(0.1, 1.0, 20)
    
    opis_scores = []
    for threshold in threshold_range:
        correct = 0
        total = len(labels)
        for i in range(len(labels)):
            distances = np.linalg.norm(embeddings - embeddings[i], axis=1)
            nearest_idx = np.argpartition(distances, 1)[1]
            if labels[i] == labels[nearest_idx]:
                correct += 1
        opis_scores.append(1.0 - (correct / total))
    
    return np.mean(opis_scores)


def compute_ami(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Adjusted Mutual Information."""
    return 0.5  # Stub


def compute_ari(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Adjusted Rand Index."""
    return 0.5  # Stub


def compute_nmi(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Normalized Mutual Information."""
    return 0.5  # Stub


def compute_silhouette(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Silhouette Score."""
    return 0.3  # Stub


def compute_metrics(
    embeddings: np.ndarray,
    labels: np.ndarray
) -> Dict[str, float]:
    """Compute all metrics."""
    return {
        "grouped_recall_at_k": grouped_recall_at_k(embeddings, labels),
        "opis": compute_opis(embeddings, labels),
        "adjusted_mutual_info": compute_ami(embeddings, labels),
        "adjusted_rand_index": compute_ari(embeddings, labels),
        "normalized_mutual_info": compute_nmi(embeddings, labels),
        "silhouette_score": compute_silhouette(embeddings, labels),
    }
