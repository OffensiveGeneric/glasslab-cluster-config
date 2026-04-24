#!/usr/bin/env python3
"""Import contrastive learning technique catalog entry for glasslab-metric-search."""

from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:18081"


def import_contrastive_learning_technique() -> None:
    """Import the contrastive learning technique catalog entry."""
    
    technique_card = {
        "name": "Contrastive Learning for Unseen Class Generalization",
        "aliases": [
            "contrastive learning",
            "contrastive representation learning",
            "metric learning",
            "deep metric learning",
            "DML",
            "siamese networks",
            "triplet loss",
            "supervised contrastive loss"
        ],
        "summary": (
            "Contrastive representation learning for generalization to unseen classes. "
            "Uses CIFAR-100 with 80/20 seen/unseen split. Implements Supervised Contrastive Loss, "
            "Triplet Loss with semi-hard/hard negative mining, and advanced evaluation metrics "
            "(Grouped Recall@K, OPIS, AMI, ARI, NMI, Silhouette)."
        ),
        "problem_types": [
            "multiclass_classification",
            "contrastive_learning",
            "metric_learning",
            "unseen_class_generalization"
        ],
        "algorithm_family": "contrastive_representation_learning",
        "specific_algorithms": [
            "supervised_contrastive_loss",
            "triplet_loss",
            "multi_similarity_loss",
            "proxy_anchor_loss",
            "resnet50_contrastive",
            "vit_base_contrastive",
            "convnext_base_contrastive"
        ],
        "automl_frameworks": ["optuna", "syne_tune", "ray_tune"],
        "preprocessing_steps": [
            "random_resized_crop",
            "random_horizontal_flip",
            "color_jitter",
            "random_grayscale",
            "normalize_cifar100"
        ],
        "loss_functions": [
            "supervised_contrastive_loss",
            "triplet_loss",
            "multi_similarity_loss",
            "proxy_anchor_loss",
            "contrastive_loss"
        ],
        "optimizers": ["adam", "sgd", "lars"],
        "hyperparameter_optimization": [
            "random_search",
            "bayesian_optimization",
            "tpe_optuna",
            "asha"
        ],
        "validation_strategies": [
            "holdout",
            "k_fold_cv",
            "stratified_split",
            "seen_unseen_split"
        ],
        "primary_metrics": [
            "grouped_recall_at_k",
            "opis",
            "adjusted_mutual_info",
            "adjusted_rand_index",
            "normalized_mutual_information",
            "silhouette_score",
            "contrastive_loss"
        ],
        "uncertainty_quantification": [
            "conformal_prediction",
            "uncertainty_toolbox"
        ],
        "python_packages": [
            "torch",
            "torchvision",
            "pytorch-metric-learning",
            "faiss-cpu",
            "umap-learn",
            "scikit-learn",
            "optuna",
            "mlxtend",
            "torchcp"
        ],
        "gpu_required": True,
        "resource_profile": "gpu-small",
        "workflow_ids": ["gpu-experiment"],
        "template_compatibility": [
            "deterministic-template",
            "pytorch-template-v1"
        ],
        "dataset_hints": [
            "cifar100",
            "cifar100_seen_unseen",
            "image_classification",
            "contrastive_learning_dataset"
        ],
        "default_dataset_uri": "s3://datasets/cifar100/",
        "default_evaluation_target": "Contrastive learning evaluation for unseen class generalization",
        "default_training_notes": (
            "Train contrastive representation on CIFAR-100 with 80 seen classes. "
            "Use 80% of training data for train-seen, 20% for val-seen. "
            "Evaluate on test-seen (80 classes) and test-unseen (20 classes). "
            "Apply strong augmentation: RandomResizedCrop, ColorJitter, RandomHorizontalFlip. "
            "Use semi-hard negative mining with margin=0.3. "
            "Batch size: 64, Learning rate: 1e-4, Temperature: 0.1."
        ),
        "default_execution_inputs": {
            "dataset_uri": "s3://datasets/cifar100/",
            "model_family": "resnet50_contrastive",
            "training_notes": (
                "Train contrastive representation on CIFAR-100 with 80 seen classes. "
                "Use 80% of training data for train-seen, 20% for val-seen. "
                "Evaluate on test-seen (80 classes) and test-unseen (20 classes)."
            ),
            "evaluation_target": "Contrastive learning evaluation for unseen class generalization",
            "validation_strategy": "stratified_seen_unseen_split",
            "pair_strategy": "class_aware_positive_negative_pairs",
            "evaluation_protocol": "contrastive_unseen_generalization",
            "label_field": "label",
            "image_field": "image",
            "negative_sampling_strategy": "semi_hard_negative_mining"
        },
        "common_failure_modes": [
            "overfitting_to_seen_classes",
            "insufficient_hard_negative_mining",
            "temperature_parameter_tuning_missing",
            "augmentation_pipeline_underparameterized",
            "threshold_inconsistency_in_retrieval"
        ],
        "source_refs": [
            "https://github.com/OffensiveGeneric/glasslab-metric-search",
            "https://arxiv.org/abs/2004.11362 (Supervised Contrastive Loss)",
            "https://arxiv.org/abs/1912.05873 (Deep Metric Learning)",
            "https://arxiv.org/abs/2305.10230 (OPIS metric)",
            "https://github.com/OffensiveGeneric/glasslab-v2"
        ],
        "notes": [
            "First priority: implement Grouped Recall@K for invariant evaluation across seen/unseen splits",
            "Second priority: compute OPIS for threshold consistency assessment",
            "Third priority: run 5x2cv paired t-test or McNemar's test for statistical validation",
            "Baseline models: DINO ViT, ResNet-50, CLIP zero-shot"
        ],
    }

    payload = {
        "import_source": "manual-contrastive-learning-spec",
        "cards": [technique_card],
        "replace_existing": False,
    }

    response = requests.post(
        f"{BASE_URL}/technique-catalog/import",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    imported = response.json()
    print(f"Imported {len(imported)} technique catalog record(s)")
    for record in imported:
        print(f"  - {record['name']} (technique_id: {record['technique_id']})")


if __name__ == "__main__":
    import_contrastive_learning_technique()
