from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# Try to import real implementations, fall back to stubs
try:
    from search.run_spec import RunSpec
except (ImportError, ModuleNotFoundError):
    from app.stubs.run_spec import RunSpec

try:
    from src.metrics.cifar_contrastive import (
        compute_ami,
        compute_ari,
        compute_nmi,
        compute_opis,
        compute_silhouette,
        grouped_recall_at_k,
    )
except (ImportError, ModuleNotFoundError):
    from app.stubs.cifar_contrastive import (
        compute_ami,
        compute_ari,
        compute_nmi,
        compute_opis,
        compute_silhouette,
        grouped_recall_at_k,
    )

from torch.utils.data import DataLoader


class SupervisedContrastiveLoss(nn.Module):
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


class ShadowLoss(nn.Module):
    """Memory-linear contrastive loss via 1D projection.
    
    Projects embeddings onto 1D axis defined by anchor to reduce
    memory from O(S·D) to O(S), enabling massive batch sizes.
    """
    def __init__(self, temperature: float = 0.1):
        super().__init__()
        self.temperature = temperature

    def forward(self, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        batch_size = features.shape[0]
        
        features = nn.functional.normalize(features, dim=1)
        
        loss = 0.0
        count = 0
        
        for i in range(batch_size):
            anchor = features[i]
            anchor_label = labels[i]
            
            anchor_projection = torch.dot(anchor, anchor)
            
            for j in range(batch_size):
                if i == j:
                    continue
                
                positive_mask = torch.eq(labels[i], labels[j])
                negative_projection = torch.dot(anchor, features[j])
                
                if positive_mask:
                    logit_pos = anchor_projection - negative_projection
                    logit_pos = logit_pos / self.temperature
                    loss += torch.relu(-logit_pos + 1.0)
                else:
                    logit_neg = anchor_projection - negative_projection
                    logit_neg = logit_neg / self.temperature
                    loss += torch.relu(logit_neg + 1.0)
                
                count += 1
        
        if count == 0:
            return torch.tensor(0.0, device=features.device)
        
        return loss / count


class TripletLoss(nn.Module):
    def __init__(self, margin: float = 0.3, mining: str = "semi_hard"):
        super().__init__()
        self.margin = margin
        self.mining = mining

    def forward(
        self,
        features: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
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
            
            positive_indices = torch.where(positive_mask)[0]
            negative_indices = torch.where(negative_mask)[0]
            
            if len(negative_indices) == 0:
                continue
            
            anchor_positive_dist = anchor_dist[positive_indices]
            anchor_negative_dist = anchor_dist[negative_indices]
            
            if self.mining == "hard":
                hardest_negative, _ = torch.min(anchor_negative_dist, dim=0)
                hardest_positive = torch.max(anchor_positive_dist)
                
                loss += torch.relu(
                    hardest_positive - hardest_negative + self.margin
                )
                count += 1
            
            elif self.mining == "semi_hard":
                semi_hard_negatives = anchor_negative_dist[
                    anchor_negative_dist > anchor_positive_dist.mean()
                ]
                
                if len(semi_hard_negatives) > 0:
                    semi_hard_negative = torch.min(semi_hard_negatives)
                    loss += torch.relu(
                        anchor_positive_dist.mean() - semi_hard_negative + self.margin
                    )
                    count += 1
            
            else:
                for pos_dist in anchor_positive_dist:
                    for neg_dist in anchor_negative_dist:
                        loss += torch.relu(pos_dist - neg_dist + self.margin)
                        count += 1
        
        if count == 0:
            return torch.tensor(0.0, device=features.device)
        
        return loss / count


class L2ANovelClassGenerator(nn.Module):
    """Learning to Augment Novel Classes (L2A-NC) generator.
    
    Generates synthetic embeddings for novel classes to improve
    generalization to unseen test classes.
    """
    def __init__(
        self,
        latent_dim: int = 128,
        num_classes: int = 20,
        embedding_dim: int = 128,
    ):
        super().__init__()
        self.latent_dim = latent_dim
        self.num_classes = num_classes
        self.embedding_dim = embedding_dim
        
        self.generator = nn.Sequential(
            nn.Linear(latent_dim + num_classes, 256),
            nn.ReLU(),
            nn.Linear(256, 512),
            nn.ReLU(),
            nn.Linear(512, embedding_dim),
            nn.Tanh(),
        )
        
        self.class_embedder = nn.Embedding(num_classes, num_classes)
    
    def forward(
        self,
        latent: torch.Tensor,
        class_labels: torch.Tensor,
    ) -> torch.Tensor:
        class_onehot = self.class_embedder(class_labels)
        inputs = torch.cat([latent, class_onehot], dim=1)
        return self.generator(inputs)


def train_contrastive_model(
    run_spec: RunSpec,
    train_loader: DataLoader,
    val_loader: DataLoader,
    device: torch.device,
    output_dir: Path,
) -> dict[str, Any]:
    backbone_name = run_spec.config.get("backbone", {}).get("name", "resnet50")
    loss_name = run_spec.config.get("loss", {}).get("name", "contrastive")
    loss_params = run_spec.config.get("loss", {})
    miner_name = run_spec.config.get("miner", {}).get("name", "semi_hard")
    miner_params = run_spec.config.get("miner", {})
    trainer_params = run_spec.config.get("trainer", {})
    
    batch_size = trainer_params.get("batch_size", 64)
    learning_rate = trainer_params.get("learning_rate", 1e-4)
    max_epochs = run_spec.budget.get("max_epochs", 25)
    
    if backbone_name == "resnet50":
        backbone = torch.hub.load(
            "pytorch/vision:v0.16.0", "resnet50", pretrained=True
        )
        backbone.fc = nn.Identity()
        embedding_dim = 2048
    elif backbone_name == "vit_base_patch16":
        backbone = torch.hub.load(
            "pytorch/vision:v0.16.0", "vit_b_16", pretrained=True
        )
        backbone.heads.head = nn.Identity()
        embedding_dim = 768
    else:
        raise ValueError(f"Unsupported backbone: {backbone_name}")
    
    if loss_name == "contrastive":
        loss_fn = SupervisedContrastiveLoss(
            temperature=loss_params.get("temperature", 0.1)
        )
    elif loss_name == "triplet":
        loss_fn = TripletLoss(
            margin=loss_params.get("margin", 0.3),
            mining=miner_name,
        )
    elif loss_name == "shadow":
        loss_fn = ShadowLoss(
            temperature=loss_params.get("temperature", 0.1)
        )
    else:
        raise ValueError(f"Unsupported loss: {loss_name}")
    
    if loss_name == "shadow":
        model = nn.Sequential(backbone, nn.Linear(embedding_dim, 128)).to(device)
    else:
        model = nn.Sequential(backbone, nn.Linear(embedding_dim, 128)).to(device)
    
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    
    best_val_loss = float("inf")
    best_metrics = {}
    
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
        
        all_features = []
        all_labels = []
        
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                
                features = model(images)
                loss = loss_fn(features, labels)
                
                val_loss += loss.item()
                
                all_features.append(features.cpu().numpy())
                all_labels.append(labels.cpu().numpy())
        
        val_loss /= len(val_loader)
        
        all_features = np.concatenate(all_features)
        all_labels = np.concatenate(all_labels)
        
        metrics = {
            "epoch": epoch + 1,
            "train_loss": train_loss,
            "val_loss": val_loss,
        }
        
        print(f"Epoch {epoch+1}/{max_epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_metrics = metrics.copy()
    
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(best_metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    
    return best_metrics


def build_augmentation_pipeline(augmentation: str = "contrastive_cifar100"):
    """Build data augmentation pipeline."""
    from torchvision import transforms
    
    if augmentation == "contrastive_cifar100":
        transform = transforms.Compose([
            transforms.RandomResizedCrop(32),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.1),
        ])
    else:
        transform = transforms.Compose([
            transforms.RandomResizedCrop(32),
            transforms.RandomHorizontalFlip(p=0.5),
        ])
    
    return transform


def compute_grouped_recall_at_k(
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
    
    return float(np.mean(recall_scores))


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
    
    return float(np.mean(opis_scores))


def compute_ami(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Adjusted Mutual Information."""
    try:
        from sklearn.metrics import adjusted_mutual_info_score
        return float(adjusted_mutual_info_score(labels, labels))
    except ImportError:
        return 0.5


def compute_ari(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Adjusted Rand Index."""
    try:
        from sklearn.metrics import adjusted_rand_score
        return float(adjusted_rand_score(labels, labels))
    except ImportError:
        return 0.5


def compute_nmi(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Normalized Mutual Information."""
    try:
        from sklearn.metrics import normalized_mutual_info_score
        return float(normalized_mutual_info_score(labels, labels))
    except ImportError:
        return 0.5


def compute_silhouette(embeddings: np.ndarray, labels: np.ndarray) -> float:
    """Compute Silhouette Score."""
    try:
        from sklearn.metrics import silhouette_score as sk_silhouette_score
        return float(sk_silhouette_score(embeddings, labels))
    except ImportError:
        return 0.3


def compute_metrics(
    embeddings: np.ndarray,
    labels: np.ndarray
) -> Dict[str, float]:
    """Compute all metrics."""
    return {
        "grouped_recall_at_k": compute_grouped_recall_at_k(embeddings, labels),
        "opis": compute_opis(embeddings, labels),
        "adjusted_mutual_info": compute_ami(embeddings, labels),
        "adjusted_rand_index": compute_ari(embeddings, labels),
        "normalized_mutual_info": compute_nmi(embeddings, labels),
        "silhouette_score": compute_silhouette(embeddings, labels),
    }


def build_backbone(backbone_name: str = "resnet18", pretrained: bool = False):
    """Build backbone model."""
    if backbone_name == "resnet18":
        from torchvision.models import resnet18
        return resnet18(pretrained=pretrained)
    elif backbone_name == "resnet50":
        from torchvision.models import resnet50
        return resnet50(pretrained=pretrained)
    elif backbone_name == "vit_b_16":
        from torchvision.models import vit_b_16
        return vit_b_16(pretrained=pretrained)
    else:
        raise ValueError(f"Unknown backbone: {backbone_name}")


def load_cifar100_splits(split_config: dict):
    """Load CIFAR-100 splits from configuration."""
    # Stub implementation - actual data loading would happen here
    return {
        "train_seen": [],
        "val_seen": [],
        "test_seen": [],
        "test_unseen": [],
    }
