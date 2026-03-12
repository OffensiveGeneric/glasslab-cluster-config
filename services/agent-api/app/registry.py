from __future__ import annotations

PIPELINE_REGISTRY = {
    'titanic_baseline': {
        'description': 'Train simple scikit-learn baselines for the Kaggle Titanic competition.',
        'supported_models': ['logistic_regression', 'random_forest', 'xgboost_optional'],
        'default_feature_profile': 'basic',
        'default_resource_profile': 'cpu-small',
    }
}

DATASET_REGISTRY = {
    'titanic': {
        'description': 'Kaggle Titanic competition dataset with train.csv and test.csv.',
        'expected_files': ['train.csv', 'test.csv'],
        'optional_files': ['gender_submission.csv', 'sample_submission.csv'],
        'mount_subpath': 'titanic',
    }
}

MODEL_REGISTRY = {
    'logistic_regression': {'family': 'sklearn', 'supports_gpu': False},
    'random_forest': {'family': 'sklearn', 'supports_gpu': False},
    'xgboost_optional': {'family': 'xgboost', 'supports_gpu': True},
}

FEATURE_PROFILE_REGISTRY = {
    'basic': {
        'description': 'Core Titanic features with simple imputations and encoding.',
    },
    'extended': {
        'description': 'Basic profile plus a small set of hand-written engineered features.',
    },
}

RESOURCE_PROFILE_REGISTRY = {
    'cpu-small': {
        'requests': {'cpu': '500m', 'memory': '1Gi'},
        'limits': {'cpu': '1', 'memory': '2Gi'},
        'node_selector': {},
        'runtime_class_name': None,
    },
    'cpu-medium': {
        'requests': {'cpu': '1', 'memory': '2Gi'},
        'limits': {'cpu': '2', 'memory': '4Gi'},
        'node_selector': {},
        'runtime_class_name': None,
    },
    'gpu-small': {
        'requests': {'cpu': '1', 'memory': '4Gi'},
        'limits': {'cpu': '2', 'memory': '6Gi', 'nvidia.com/gpu': '1'},
        'node_selector': {'glasslab.io/gpu-candidate': 'true'},
        'runtime_class_name': 'nvidia',
    },
}

COMPARE_TO_OPTIONS = {'none', 'latest_successful'}
ALLOWED_SPEC_KEYS = {
    'pipeline',
    'dataset',
    'models',
    'feature_profile',
    'resource_profile',
    'compare_to',
    'produce_submission',
}


def list_pipelines() -> list[dict]:
    return [
        {
            'name': name,
            **payload,
        }
        for name, payload in sorted(PIPELINE_REGISTRY.items())
    ]


def list_datasets() -> list[dict]:
    return [
        {
            'name': name,
            **payload,
        }
        for name, payload in sorted(DATASET_REGISTRY.items())
    ]
