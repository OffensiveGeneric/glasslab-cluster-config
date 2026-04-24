"""Contrastive learning runner for CIFAR-100 unseen class generalization."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
from torch.utils.data import DataLoader

# Import common runner utilities
from services.runner.app.runner import write_json


class SupervisedContrastiveLoss(nn.Module):
    """Supervised Contrastive Loss from https://arxiv.org/abs/2004.11362."""

    def __init__(self, temperature: float = 0.1):
        super().__init__()
        self.temperature = temperature

    def forward(self, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        batch_size = features.shape[0]
        
        features = nn.functional.normalize(features, dim=1)
        
        similarity_matrix = torch.matmul(features, features.T)
        mask = torch.eq(labels.unsqueeze(1), labels.unsqueeze(0)).float()
        
        similarity_matrix = similarity_matrix / self.temperature
        
        logits_max, _ = torch.max(similarity_matrix, dim=1, keepdim=True)
        logits = similarity_matrix - logits_max.detach()
        
        mask = mask.bool()
        mask = mask ^ torch.eye(batch_size, dtype=torch.bool, device=mask.device)
        
        logits_mask = torch.ones_like(mask).bool()
        logits_mask = logits_mask ^ torch.eye(batch_size, dtype=torch.bool, device=logits_mask.device)
        
        exp_logits = torch.exp(logits) * logits_mask
        log_prob = logits - torch.log(exp_logits.sum(1, keepdim=True))
        
        mean_log_prob_pos = (mask * log_prob).sum(1) / mask.sum(1)
        
        loss = -mean_log_prob_pos.mean()
        return loss


class TripletLoss(nn.Module):
    """Triplet Loss with semi-hard/hard negative mining."""

    def __init__(self, margin: float = 0.3, mining: str = "semi_hard"):
        super().__init__()
        self.margin = margin
        self.mining = mining

    def forward(self, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        batch_size = features.shape[0]
        features = nn.functional.normalize(features, dim=1)
        distances = torch.cdist(features, features, p=2)
        labels = labels.unsqueeze(1)
        mask = torch.eq(labels, labels.T).bool()
        
        loss = 0.0
        count = 0
        
        for i in range(batch_size):
            anchor_dist = distances[i]
            anchor_label = labels[i]
            
            positive_mask = mask[i].bool()
            negative_mask = (~mask[i]).bool()
            
            if not positive_mask.sum() > 1:
                continue
            if len(torch.where(negative_mask)[0]) == 0:
                continue
            
            positive_indices = torch.where(positive_mask)[0]
            negative_indices = torch.where(negative_mask)[0]
            
            if self.mining == "hard":
                hardest_negative = torch.min(anchor_dist[negative_indices])
                hardest_positive = torch.max(anchor_dist[positive_indices])
                loss += torch.relu(hardest_positive - hardest_negative + self.margin)
                count += 1
            
            elif self.mining == "semi_hard":
                anchor_positive_dist = anchor_dist[positive_indices]
                anchor_negative_dist = anchor_dist[negative_indices]
                semi_hard_negatives = anchor_negative_dist[anchor_negative_dist > anchor_positive_dist.mean()]
                
                if len(semi_hard_negatives) > 0:
                    semi_hard_negative = torch.min(semi_hard_negatives)
                    loss += torch.relu(anchor_positive_dist.mean() - semi_hard_negative + self.margin)
                    count += 1
            
            else:  # random mining
                for pos_idx in positive_indices:
                    for neg_idx in negative_indices:
                        loss += torch.relu(anchor_dist[pos_idx] - anchor_dist[neg_idx] + self.margin)
                        count += 1
        
        if count == 0:
            return torch.tensor(0.0, device=features.device)
        return loss / count


def build_backbone(backbone_name: str) -> tuple[nn.Module, int]:
    """Build backbone model and return embedding dimension."""
    if backbone_name == "resnet50":
        backbone = torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.IMAGENET1K_V1)
        backbone.fc = nn.Identity()
        embedding_dim = 2048
    elif backbone_name == "vit_base_patch16":
        backbone = torchvision.models.vit_b_16(weights=torchvision.models.ViT_B_16_Weights.IMAGENET1K_V1)
        backbone.heads.head = nn.Identity()
        embedding_dim = 768
    elif backbone_name == "convnext_base":
        backbone = torchvision.models.convnext_base(weights=torchvision.models.ConvNeXt_Base_Weights.IMAGENET1K_V1)
        backbone.classifier[2] = nn.Identity()
        embedding_dim = 1024
    else:
        raise ValueError(f"Unsupported backbone: {backbone_name}")
    
    return backbone, embedding_dim


def build_augmentation_pipeline(augmentation: str = "contrastive_cifar100") -> torchvision.transforms.Compose:
    """Build contrastive augmentation pipeline."""
    if augmentation == "contrastive_cifar100":
        transform = torchvision.transforms.Compose([
            torchvision.transforms.RandomResizedCrop(32),
            torchvision.transforms.RandomHorizontalFlip(p=0.5),
            torchvision.transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.1),
            torchvision.transforms.RandomGrayscale(p=0.2),
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Normalize(mean=[0.5071, 0.4865, 0.4409], std=[0.2673, 0.2564, 0.2762]),
        ])
    else:
        raise ValueError(f"Unsupported augmentation: {augmentation}")
    
    return transform


def load_cifar100_splits(
    root: str | Path,
    seen_classes: list[int],
    unseen_classes: list[int],
    augment: bool = True,
    batch_size: int = 64,
    num_workers: int = 4,
) -> dict[str, DataLoader]:
    """Load CIFAR-100 with seen/unseen splits."""
    root = Path(root).expanduser()
    
    transform = build_augmentation_pipeline() if augment else torchvision.transforms.Compose([
        torchvision.transforms.ToTensor(),
        torchvision.transforms.Normalize(mean=[0.5071, 0.4865, 0.4409], std=[0.2673, 0.2564, 0.2762]),
    ])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        train_seen = torchvision.datasets.CIFAR100(
            root=tmpdir, train=True, download=True, transform=transform
        )
        test_seen = torchvision.datasets.CIFAR100(
            root=tmpdir, train=False, download=True, transform=transform
        )
        test_unseen = torchvision.datasets.CIFAR100(
            root=tmpdir, train=False, download=True, transform=transform
        )
    
    # Filter by class
    def filter_by_classes(dataset: torchvision.datasets.CIFAR100, classes: list[int]) -> torchvision.datasets.CIFAR100:
        mask = np.isin(dataset.targets, classes)
        dataset.data = dataset.data[mask]
        dataset.targets = [int(np.where(np.array(classes) == label)[0][0]) for label in np.array(dataset.targets)[mask]]
        return dataset
    
    train_seen = filter_by_classes(train_seen, seen_classes)
    test_seen = filter_by_classes(test_seen, seen_classes)
    test_unseen = filter_by_classes(test_unseen, unseen_classes)
    
    return {
        "train_seen": DataLoader(train_seen, batch_size=batch_size, shuffle=True, num_workers=num_workers),
        "val_seen": DataLoader(test_seen, batch_size=batch_size, shuffle=False, num_workers=num_workers),
        "test_seen": DataLoader(test_seen, batch_size=batch_size, shuffle=False, num_workers=num_workers),
        "test_unseen": DataLoader(test_unseen, batch_size=batch_size, shuffle=False, num_workers=num_workers),
    }


def compute_grouped_recall_at_k(
    embeddings: np.ndarray,
    labels: np.ndarray,
    k: int = 10,
    n_groups: int = 4,
) -> float:
    """Compute Grouped Recall@K for invariant evaluation across class counts."""
    n_samples = len(labels)
    samples_per_group = n_samples // n_groups
    
    grouped_rk_scores = []
    for i in range(n_groups):
        start_idx = i * samples_per_group
        end_idx = start_idx + samples_per_group
        
        group_embeddings = embeddings[start_idx:end_idx]
        group_labels = labels[start_idx:end_idx]
        
        distances = np.linalg.norm(group_embeddings[:, np.newaxis] - group_embeddings[np.newaxis, :], axis=2)
        
        recall_scores = []
        for j in range(len(group_embeddings)):
            row_distances = distances[j]
            neighbor_indices = np.argsort(row_distances)[1:k+1]
            neighbor_labels = group_labels[neighbor_indices]
            
            correct = np.sum(neighbor_labels == group_labels[j])
            recall = correct / min(k, len(neighbor_labels))
            recall_scores.append(recall)
        
        grouped_rk_scores.append(np.mean(recall_scores))
    
    return float(np.mean(grouped_rk_scores))


def compute_opis(
    embeddings: np.ndarray,
    labels: np.ndarray,
    threshold_range: np.ndarray | None = None,
) -> float:
    """Compute Operating-Point-Inconsistency Score."""
    if threshold_range is None:
        threshold_range = np.linspace(0.1, 2.0, 50)
    
    n_samples = len(labels)
    distances = np.linalg.norm(embeddings[:, np.newaxis] - embeddings[np.newaxis, :], axis=2)
    
    f1_scores = []
    for thresh in threshold_range:
        predictions = (distances < thresh).astype(int)
        
        tp = np.sum((predictions == 1) & (labels[:, np.newaxis] == labels[np.newaxis, :]))
        fp = np.sum((predictions == 1) & (labels[:, np.newaxis] != labels[np.newaxis, :]))
        fn = np.sum((predictions == 0) & (labels[:, np.newaxis] == labels[np.newaxis, :]))
        
        precision = tp / (tp + fp + 1e-8)
        recall = tp / (tp + fn + 1e-8)
        f1 = 2 * precision * recall / (precision + recall + 1e-8)
        f1_scores.append(f1)
    
    f1_scores = np.array(f1_scores)
    mean_f1 = np.mean(f1_scores)
    opis = np.mean(np.abs(f1_scores - mean_f1))
    
    return float(opis)


def compute_metrics(
    embeddings: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    """Compute all contrastive learning metrics."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import (
        adjusted_mutual_info_score,
        adjusted_rand_score,
        normalized_mutual_info_score,
        silhouette_score,
    )
    
    # Cluster for unsupervised metrics
    kmeans = KMeans(n_clusters=len(np.unique(labels)), random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(embeddings)
    
    return {
        "grouped_recall_at_k": compute_grouped_recall_at_k(embeddings, labels),
        "opis": compute_opis(embeddings, labels),
        "adjusted_mutual_info": float(adjusted_mutual_info_score(labels, cluster_labels)),
        "adjusted_rand_index": float(adjusted_rand_score(labels, cluster_labels)),
        "normalized_mutual_info": float(normalized_mutual_info_score(labels, cluster_labels)),
        "silhouette_score": float(silhouette_score(embeddings, labels)),
    }


def train_contrastive_model(
    train_loader: DataLoader,
    val_loader: DataLoader,
    device: torch.device,
    loss_name: str = "contrastive",
    margin: float = 0.3,
    temperature: float = 0.1,
    batch_size: int = 64,
    learning_rate: float = 1e-4,
    max_epochs: int = 25,
    backbone_name: str = "resnet50",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Train contrastive learning model."""
    backbone, embedding_dim = build_backbone(backbone_name)
    
    if loss_name == "contrastive":
        loss_fn = SupervisedContrastiveLoss(temperature=temperature)
    elif loss_name == "triplet":
        loss_fn = TripletLoss(margin=margin, mining="semi_hard")
    else:
        raise ValueError(f"Unsupported loss: {loss_name}")
    
    model = nn.Sequential(backbone, nn.Linear(embedding_dim, 128)).to(device)
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    
    best_val_loss = float("inf")
    best_metrics = {}
    all_embeddings = []
    all_labels = []
    
    for epoch in range(max_epochs):
        model.train()
        train_loss = 0.0
        
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            
            features = model(images)
            loss = loss_fn(features, labels)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        model.eval()
        val_loss = 0.0
        all_embeddings = []
        all_labels = []
        
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                features = model(images)
                loss = loss_fn(features, labels)
                val_loss += loss.item()
                
                all_embeddings.append(features.cpu().numpy())
                all_labels.append(labels.cpu().numpy())
        
        val_loss /= len(val_loader)
        all_embeddings = np.concatenate(all_embeddings)
        all_labels = np.concatenate(all_labels)
        
        metrics = compute_metrics(all_embeddings, all_labels)
        metrics["train_loss"] = train_loss
        metrics["val_loss"] = val_loss
        
        print(f"Epoch {epoch+1}/{max_epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_metrics = metrics.copy()
            
            if output_dir:
                # Save model
                torch.save(model.state_dict(), output_dir / "model.pt")
                
                # Save metrics
                write_json(output_dir / "metrics.json", best_metrics)
                
                # Save embeddings
                np.save(output_dir / "embeddings.npy", all_embeddings)
                np.save(output_dir / "labels.npy", all_labels)
    
    return best_metrics
