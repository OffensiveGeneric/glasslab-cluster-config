from fastapi.testclient import TestClient

from app.main import Settings, create_app


def test_help_command_returns_local_text() -> None:
    client = TestClient(create_app(settings=Settings(), requester=lambda *args, **kwargs: ("", {})))
    response = client.post("/dispatch", json={"message": "!help"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is True
    assert payload["forward_to_openclaw"] is False
    assert "!research <topic>" in payload["response_text"]


def test_research_command_calls_start_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        assert path == "/research-sessions/start-literature-search"
        assert method == "POST"
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "session": {"title": "Forged Art Detection"},
                "paper_intake_queue": {"candidates": [{"paper_id": "a"}], "coverage_summary": {"mode": "external"}},
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!research forged art detection with computer vision methods"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "research"
    assert "Started literature search" in payload["response_text"]
    assert len(calls) == 1


def test_more_papers_prefers_external_search() -> None:
    def fake_requester(settings, path, method="GET", body=None):
        assert path == "/research-sessions/latest/skills/external-literature-search"
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "candidates": [{"paper_id": "a"}, {"paper_id": "b"}],
                "coverage_summary": {"mode": "external"},
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!more-papers"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "more-papers"
    assert "external literature search" in payload["response_text"]


def test_add_paper_routes_to_manual_queue() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"candidates": [{"title": "Manual paper candidate"}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add-paper https://arxiv.org/abs/2401.12345"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add-paper"
    assert calls[0][0] == "/research-sessions/latest/paper-intake-queue/manual-paper"


def test_run_command_routes_to_session_run_creation() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {"session": {"session_id": "session-123"}},
            )
        return (
            f"{settings.workflow_api_url}{path}",
            {"run_id": "run-123", "workflow_id": "gpu-experiment"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!run"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "run"
    assert calls[0][0] == "/research-sessions/latest/context"
    assert calls[1][0] == "/research-sessions/session-123/skills/design"
    assert calls[2][0] == "/research-sessions/session-123/runs/from-design"


def test_preflight_command_bootstraps_design_before_fetching_preflight() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {"session": {"session_id": "session-123"}},
            )
        if path.endswith("/execution-preflight"):
            return (
                f"{settings.workflow_api_url}{path}",
                {"workflow_id": "gpu-experiment", "blocking_issues": [], "warnings": ["ok"]},
            )
        return (f"{settings.workflow_api_url}{path}", {"design_id": "design-123"})

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!preflight"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "preflight"
    assert calls[0][0] == "/research-sessions/latest/context"
    assert calls[1][0] == "/research-sessions/session-123/skills/design"
    assert calls[2][0] == "/research-sessions/session-123/execution-preflight"


def test_interpret_command_routes_to_transition() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"interpretation_id": "interp-123", "preferred_workflow_id": "gpu-experiment"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!interpret"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "interpret"
    assert calls[0][0] == "/research-sessions/latest/transitions/create-interpretation"


def test_autoresearch_summary_command_routes_to_summary_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {"session": {"session_id": "session-123"}},
            )
        return (
            f"{settings.workflow_api_url}{path}",
            {"campaign": {"campaign_id": "camp-123"}, "recommended_model": "vit-base"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!autoresearch"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "autoresearch"
    assert calls[0][0] == "/research-sessions/latest/context"
    assert calls[1][0] == "/research-sessions/session-123/autoresearch-summary"


def test_start_autoresearch_resolves_session_before_transition() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {"session": {"session_id": "session-123"}},
            )
        return (
            f"{settings.workflow_api_url}{path}",
            {"campaign_id": "camp-123", "objective": "test objective"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!start-autoresearch"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "start-autoresearch"
    assert calls[0][0] == "/research-sessions/latest/context"
    assert calls[1][0] == "/research-sessions/session-123/transitions/start-autoresearch-campaign"


def test_non_command_turns_forward_to_openclaw() -> None:
    client = TestClient(create_app(settings=Settings(), requester=lambda *args, **kwargs: ("", {})))
    response = client.post("/dispatch", json={"message": "what do you think of this paper?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is False
    assert payload["forward_to_openclaw"] is True
