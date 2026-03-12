from __future__ import annotations

import json
from json import JSONDecodeError

from .qwen_client import QwenClient, QwenClientError
from .schemas import PlannerDecision, PlannerSpec


PLANNER_SYSTEM_PROMPT = """You are a planner for approved lab workflows.
The only supported workflow is the Kaggle Titanic competition baseline.
Output valid JSON only.
Never invent pipelines, datasets, models, feature profiles, or resource profiles.
Do not output shell commands, Python, or YAML.
Allowed values:
- pipeline: titanic_baseline
- dataset: titanic
- models: logistic_regression, random_forest, xgboost_optional
- feature_profile: basic, extended
- resource_profile: cpu-small, cpu-medium, gpu-small
- compare_to: none, latest_successful
Schema:
{
  "pipeline": "titanic_baseline",
  "dataset": "titanic",
  "models": ["logistic_regression", "random_forest"],
  "feature_profile": "basic",
  "resource_profile": "cpu-small",
  "compare_to": "none",
  "produce_submission": true
}
"""


class PlannerError(RuntimeError):
    """Raised when a plain-English request cannot be normalized safely."""


def plan_request(request_text: str, qwen_client: QwenClient) -> PlannerDecision:
    warnings: list[str] = []
    raw_output: str | None = None

    try:
        response = qwen_client.chat(
            [
                {'role': 'system', 'content': PLANNER_SYSTEM_PROMPT},
                {
                    'role': 'user',
                    'content': f'Normalize this request into the approved schema only: {request_text}',
                },
            ]
        )
        raw_output = response.content
        parsed = _load_json_object(raw_output)
        spec = PlannerSpec.model_validate(parsed)
        return PlannerDecision(spec=spec, source='model', raw_output=raw_output)
    except (PlannerError, QwenClientError, JSONDecodeError, ValueError) as exc:
        fallback = fallback_plan_request(request_text)
        if fallback is None:
            raise PlannerError(f'planner failed and no deterministic fallback matched: {exc}') from exc
        warnings.append(str(exc))
        spec = PlannerSpec.model_validate(fallback)
        return PlannerDecision(
            spec=spec,
            source='fallback',
            raw_output=raw_output,
            warnings=warnings,
        )


def fallback_plan_request(request_text: str) -> dict | None:
    lower_request = request_text.lower()
    if 'titanic' not in lower_request:
        return None

    models: list[str] = []
    if 'logistic regression' in lower_request or 'logistic_regression' in lower_request:
        models.append('logistic_regression')
    if 'random forest' in lower_request or 'random_forest' in lower_request:
        models.append('random_forest')
    if 'xgboost' in lower_request:
        models.append('xgboost_optional')
    if not models:
        models = ['logistic_regression', 'random_forest']

    resource_profile = 'cpu-small'
    if 'gpu' in lower_request:
        resource_profile = 'gpu-small'
    elif 'cpu-medium' in lower_request or 'medium' in lower_request:
        resource_profile = 'cpu-medium'

    feature_profile = 'extended' if 'extended' in lower_request else 'basic'
    compare_to = 'latest_successful' if 'latest_successful' in lower_request or 'latest successful' in lower_request else 'none'
    produce_submission = any(token in lower_request for token in ['submission', 'submit', 'kaggle'])

    return {
        'pipeline': 'titanic_baseline',
        'dataset': 'titanic',
        'models': models,
        'feature_profile': feature_profile,
        'resource_profile': resource_profile,
        'compare_to': compare_to,
        'produce_submission': produce_submission,
    }


def _load_json_object(raw_output: str) -> dict:
    candidate = raw_output.strip()
    if candidate.startswith('```'):
        parts = candidate.split('```')
        candidate = next((part for part in parts if '{' in part and '}' in part), candidate)
    json_start = candidate.find('{')
    json_end = candidate.rfind('}')
    if json_start == -1 or json_end == -1:
        raise PlannerError('planner output did not contain a JSON object')
    json_payload = candidate[json_start : json_end + 1]
    return json.loads(json_payload)
