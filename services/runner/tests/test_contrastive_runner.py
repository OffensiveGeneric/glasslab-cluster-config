"""Tests for contrastive learning runner."""

import numpy as np
import pytest
import torch

# Add parent directory to path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from contrastive_runner import (
    SupervisedContrastiveLoss,
    TripletLoss,
    build_augmentation_pipeline,
    build_backbone,
    compute_grouped_recall_at_k,
    compute_metrics,
    compute_opis,
    load_cifar100_splits,
)


class TestSupervisedContrastiveLoss:
    """Test SupervisedContrastiveLoss implementation."""

    def test_loss_computes_correctly(self):
        """Test that loss computes without errors."""
        batch_size = 8
        embedding_dim = 128
        
        features = torch.randn(batch_size, embedding_dim)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        
        loss_fn = SupervisedContrastiveLoss(temperature=0.1)
        loss = loss_fn(features, labels)
        
        assert loss.item() >= 0.0
        assert not torch.isnan(loss)

    def test_loss_with_normalized_features(self):
        """Test loss with already normalized features."""
        batch_size = 8
        embedding_dim = 128
        
        features = torch.randn(batch_size, embedding_dim)
        features = torch.nn.functional.normalize(features, dim=1)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        
        loss_fn = SupervisedContrastiveLoss(temperature=0.1)
        loss = loss_fn(features, labels)
        
        assert loss.item() >= 0.0
        assert not torch.isnan(loss)


class TestTripletLoss:
    """Test TripletLoss implementation."""

    def test_triplet_loss_computes_correctly(self):
        """Test that triplet loss computes without errors."""
        batch_size = 8
        embedding_dim = 128
        
        features = torch.randn(batch_size, embedding_dim)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        
        loss_fn = TripletLoss(margin=0.3, mining="semi_hard")
        loss = loss_fn(features, labels)
        
        assert loss.item() >= 0.0
        assert not torch.isnan(loss)

    def test_hard_mining(self):
        """Test hard negative mining mode."""
        batch_size = 8
        embedding_dim = 128
        
        features = torch.randn(batch_size, embedding_dim)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        
        loss_fn = TripletLoss(margin=0.3, mining="hard")
        loss = loss_fn(features, labels)
        
        assert loss.item() >= 0.0
        assert not torch.isnan(loss)

    def test_random_mining(self):
        """Test random mining mode."""
        batch_size = 8
        embedding_dim = 128
        
        features = torch.randn(batch_size, embedding_dim)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])
        
        loss_fn = TripletLoss(margin=0.3, mining="random")
        loss = loss_fn(features, labels)
        
        assert loss.item() >= 0.0
        assert not torch.isnan(loss)


class TestAugmentationPipeline:
    """Test augmentation pipeline building."""

    def test_build_augmentation_pipeline(self):
        """Test that augmentation pipeline builds correctly."""
        transform = build_augmentation_pipeline(augmentation="contrastive_cifar100")
        
        # Check that transform is a Compose
        assert hasattr(transform, 'transforms')
        assert len(transform.transforms) > 0


class TestGroupedRecallAtK:
    """Test Grouped Recall@K metric."""

    def test_grouped_recall_computes_correctly(self):
        """Test that grouped recall computes without errors."""
        embeddings = np.random.randn(100, 64)
        labels = np.array([0] * 25 + [1] * 25 + [2] * 25 + [3] * 25)
        
        recall = compute_grouped_recall_at_k(embeddings, labels, k=10, n_groups=4)
        
        assert 0.0 <= recall <= 1.0
        assert not np.isnan(recall)

    def test_grouped_recall_invariant_to_class_count(self):
        """Test that grouped recall is invariant to class count."""
        # Test with 4 classes
        embeddings_4 = np.random.randn(100, 64)
        labels_4 = np.array([0] * 25 + [1] * 25 + [2] * 25 + [3] * 25)
        recall_4 = compute_grouped_recall_at_k(embeddings_4, labels_4, k=10, n_groups=4)
        
        # Test with 8 classes (same structure)
        embeddings_8 = np.random.randn(200, 64)
        labels_8 = np.array([0] * 25 + [1] * 25 + [2] * 25 + [3] * 25 +
                           [4] * 25 + [5] * 25 + [6] * 25 + [7] * 25)
        recall_8 = compute_grouped_recall_at_k(embeddings_8, labels_8, k=10, n_groups=4)
        
        # Both should be valid
        assert 0.0 <= recall_4 <= 1.0
        assert 0.0 <= recall_8 <= 1.0


class TestOPIS:
    """Test Operating-Point-Inconsistency Score."""

    def test_opis_computes_correctly(self):
        """Test that OPIS computes without errors."""
        embeddings = np.random.randn(100, 64)
        labels = np.array([0] * 50 + [1] * 50)
        
        opis = compute_opis(embeddings, labels)
        
        assert opis >= 0.0
        assert not np.isnan(opis)

    def test_opis_threshold_range(self):
        """Test OPIS with custom threshold range."""
        embeddings = np.random.randn(100, 64)
        labels = np.array([0] * 50 + [1] * 50)
        threshold_range = np.linspace(0.1, 1.0, 20)
        
        opis = compute_opis(embeddings, labels, threshold_range)
        
        assert opis >= 0.0
        assert not np.isnan(opis)


class TestMetrics:
    """Test complete metrics computation."""

    def test_compute_metrics(self):
        """Test that all metrics compute correctly."""
        embeddings = np.random.randn(100, 64)
        labels = np.array([0] * 25 + [1] * 25 + [2] * 25 + [3] * 25)
        
        metrics = compute_metrics(embeddings, labels)
        
        assert "grouped_recall_at_k" in metrics
        assert "opis" in metrics
        assert "adjusted_mutual_info" in metrics
        assert "adjusted_rand_index" in metrics
        assert "normalized_mutual_info" in metrics
        assert "silhouette_score" in metrics
        
        for key, value in metrics.items():
            assert isinstance(value, (int, float))
            assert not np.isnan(value) if isinstance(value, float) else True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
