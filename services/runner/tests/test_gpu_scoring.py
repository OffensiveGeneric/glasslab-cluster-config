from app.runner import infer_gpu_technique_alignment


def test_infer_gpu_technique_alignment_is_generic() -> None:
    best_model, score, components = infer_gpu_technique_alignment(
        evaluation_target='roc auc',
        model_family='tabular classification',
        training_notes='Use boosted tree baselines and calibrated validation on a structured dataset.',
        technique_candidate_models=['xgboost', 'lightgbm'],
        technique_task_type='binary classification',
        technique_metrics=['roc_auc', 'brier_score'],
        technique_loss_or_distance='log_loss',
    )

    assert best_model == 'xgboost'
    assert score >= 0.6
    assert components['candidate_contract'] >= 0.45
    assert components['metric_contract'] >= 0.45
