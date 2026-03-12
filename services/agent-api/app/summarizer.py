from __future__ import annotations

import json

from .config import Settings
from .qwen_client import QwenClient


SUMMARY_SYSTEM_PROMPT = """Summarize a Kaggle Titanic baseline experiment in 4 to 6 sentences.
Include which models ran, which model won, the validation metric, and whether a submission file was produced.
Be concrete and brief.
"""


class ResultSummarizer:
    def __init__(self, settings: Settings, qwen_client: QwenClient | None = None):
        self.settings = settings
        self.qwen_client = qwen_client

    def summarize_result(self, result_payload: dict) -> str:
        if self.settings.llm_summary_enabled and self.qwen_client is not None:
            try:
                response = self.qwen_client.chat(
                    [
                        {'role': 'system', 'content': SUMMARY_SYSTEM_PROMPT},
                        {'role': 'user', 'content': json.dumps(result_payload, sort_keys=True)},
                    ],
                    max_tokens=180,
                )
                summary = response.content.strip()
                if summary:
                    return summary
            except Exception:
                pass
        return deterministic_summary(result_payload)


def deterministic_summary(result_payload: dict) -> str:
    models = ', '.join(result_payload.get('models_ran', []))
    winning_model = result_payload.get('best_model', 'unknown model')
    metric_name = result_payload.get('metric_name', 'accuracy')
    metric_value = result_payload.get('best_metric')
    metric_text = 'unavailable' if metric_value is None else f'{metric_value:.4f}'
    submission_created = result_payload.get('submission_created', False)
    artifact_dir = result_payload.get('artifact_dir', 'unknown artifact directory')
    if submission_created:
        submission_sentence = 'A Kaggle-compatible submission.csv was produced.'
    else:
        submission_sentence = 'No submission.csv was produced.'
    return (
        f'Ran the Titanic baseline with {models}. '
        f'{winning_model} won on validation with {metric_name} {metric_text}. '
        f'{submission_sentence} '
        f'Artifacts were written under {artifact_dir}.'
    )
