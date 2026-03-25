from fastapi.testclient import TestClient

from app.main import app, rank_workflow_families
from app.models import WorkflowFamilyRankRequest


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_ranker_prefers_literature_workflow_for_paper_request() -> None:
    request = WorkflowFamilyRankRequest(
        request_id='intake-1',
        query='Read this paper and derive a bounded experiment design from the literature notes.',
        hints={'source_type': 'paper-link'},
        candidates=[
            {
                'workflow_id': 'generic-tabular-benchmark',
                'summary': 'Run an approved tabular benchmark against a declared dataset.',
            },
            {
                'workflow_id': 'literature-to-experiment',
                'summary': 'Derive a bounded experiment design from a paper or literature notes.',
            },
        ],
    )

    response = rank_workflow_families(request)

    assert response.ranked_candidates[0].workflow_id == 'literature-to-experiment'
    assert response.ranked_candidates[0].score > response.ranked_candidates[1].score


def test_ranker_endpoint_prefers_tabular_workflow_for_dataset_request() -> None:
    client = TestClient(app)
    response = client.post(
        '/rank/workflow-family',
        json={
            'request_id': 'intake-2',
            'query': 'Benchmark approved models on a tabular dataset using the train and test CSV files.',
            'hints': {'dataset_name': 'titanic'},
            'candidates': [
                {
                    'workflow_id': 'literature-to-experiment',
                    'summary': 'Derive a bounded experiment design from a paper or literature notes.',
                },
                {
                    'workflow_id': 'generic-tabular-benchmark',
                    'summary': 'Run an approved tabular benchmark against a declared dataset.',
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['ranked_candidates'][0]['workflow_id'] == 'generic-tabular-benchmark'
    assert payload['ranking_basis'] == 'deterministic lexical overlap plus workflow-specific hint bonuses'
