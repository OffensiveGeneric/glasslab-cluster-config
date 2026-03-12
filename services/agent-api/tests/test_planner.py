import pytest

from app.planner import PlannerError, plan_request
from app.qwen_client import ChatResponse, QwenClientError


class BrokenQwenClient:
    def chat(self, messages, max_tokens=None):
        return ChatResponse(content='not-json-at-all', raw_payload={})


class UnavailableQwenClient:
    def chat(self, messages, max_tokens=None):
        raise QwenClientError('connection refused')


def test_planner_falls_back_for_common_titanic_request() -> None:
    decision = plan_request(
        'Run a Titanic baseline with logistic regression and random forest, compare them, and prepare a submission file.',
        BrokenQwenClient(),
    )

    assert decision.source == 'fallback'
    assert decision.spec.models == ['logistic_regression', 'random_forest']
    assert decision.spec.produce_submission is True


def test_planner_falls_back_for_connection_failure() -> None:
    decision = plan_request(
        'Run a Titanic baseline with logistic regression and random forest, compare them, and prepare a submission file.',
        UnavailableQwenClient(),
    )

    assert decision.source == 'fallback'
    assert decision.spec.models == ['logistic_regression', 'random_forest']
    assert any('connection refused' in warning for warning in decision.warnings)


def test_planner_rejects_unrelated_request_when_model_fails() -> None:
    with pytest.raises(PlannerError):
        plan_request('Train a house price model.', BrokenQwenClient())
