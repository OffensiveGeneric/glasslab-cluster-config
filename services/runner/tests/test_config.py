import json

from app.config import Settings


def test_gpu_spec_backfills_technique_context_from_manifest() -> None:
    settings = Settings(
        spec_json=json.dumps(
            {
                'pipeline': 'gpu_experiment',
                'dataset': 's3://datasets/vision/train',
                'dataset_uri': 's3://datasets/vision/train',
                'model_family': 'lightweight replication',
                'training_notes': 'bounded gpu run',
                'evaluation_target': 'embedding retrieval auc',
                'validation_strategy': 'holdout',
                'validation_split': '0.2',
                'models': ['pytorch-template-v1'],
                'feature_profile': 'gpu_ml',
                'resource_profile': 'gpu-small',
                'compare_to': 'baseline',
                'produce_submission': False,
            }
        ),
        manifest_json=json.dumps(
            {
                'inputs': {
                    'technique_candidate_models': ['vision_transformer', 'clip'],
                    'technique_baseline_models': ['pytorch-template-v1'],
                    'technique_loss_or_distance': 'contrastive_loss',
                    'technique_task_type': 'lightweight replication',
                    'technique_metrics': ['embedding_retrieval_auc'],
                }
            }
        ),
    )

    spec = settings.parsed_spec
    assert spec['technique_candidate_models'] == ['vision_transformer', 'clip']
    assert spec['technique_baseline_models'] == ['pytorch-template-v1']
    assert spec['technique_loss_or_distance'] == 'contrastive_loss'
    assert spec['technique_task_type'] == 'lightweight replication'
    assert spec['technique_metrics'] == ['embedding_retrieval_auc']
