from fastapi.testclient import TestClient

from app.main import Settings, create_app


def test_help_command_returns_local_text() -> None:
    client = TestClient(create_app(settings=Settings(), requester=lambda *args, **kwargs: ("", {})))
    response = client.post("/dispatch", json={"message": "!help"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is True
    assert payload["forward_to_openclaw"] is False
    assert "!start <topic>" in payload["response_text"]
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


def test_start_command_alias_calls_start_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        assert path == "/research-sessions/start-literature-search"
        assert method == "POST"
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "session": {"title": "Artist Similarity"},
                "paper_intake_queue": {"candidates": [], "coverage_summary": {"mode": "external"}},
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!start artist similarity metric learning"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "start"
    assert "Started literature search" in payload["response_text"]
    assert len(calls) == 1


def test_new_session_command_creates_session_without_literature_search() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        assert path == "/research-sessions"
        assert method == "POST"
        return (
            f"{settings.workflow_api_url}{path}",
            {"session_id": "session-123", "title": "Artist Similarity", "goal_statement": "artist similarity metric learning"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!new-session artist similarity metric learning"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "new-session"
    assert "Created research session" in payload["response_text"]
    assert calls[0][0] == "/research-sessions"


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


def test_add_pdf_routes_to_manual_queue_with_pdf_url() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"candidates": [{"title": "Manual PDF candidate"}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add-pdf https://example.org/paper.pdf"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add-pdf"
    assert calls[0][0] == "/research-sessions/latest/paper-intake-queue/manual-paper"
    assert calls[0][2]["pdf_url"] == "https://example.org/paper.pdf"


def test_add_pdf_uses_pinned_session_when_provided() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"candidates": [{"title": "Manual PDF candidate"}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post(
        "/dispatch",
        json={
            "message": "!add-pdf https://example.org/paper.pdf",
            "session_id": "session-123",
        },
    )
    assert response.status_code == 200
    assert calls[0][0] == "/research-sessions/session-123/paper-intake-queue/manual-paper"


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


def test_status_command_adds_campaign_summary_when_present() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {
                    "session": {"session_id": "session-123", "title": "DreamSim", "goal_statement": "replicate dreamsim"},
                    "paper_intake_queue": {"status": "ready", "candidates": [{"id": "a"}]},
                },
            )
        return (
            f"{settings.workflow_api_url}{path}",
            {"campaign": {"status": "active"}, "iterations": [{}, {}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!status"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "status"
    assert "Autoresearch campaign: active with 2 iteration(s)." in payload["response_text"]


def test_status_uses_pinned_session_context_when_provided() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/session-123/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {
                    "session": {"session_id": "session-123", "title": "Pinned", "goal_statement": "pinned goal"},
                    "paper_intake_queue": {"status": "ready", "candidates": []},
                },
            )
        return (
            f"{settings.workflow_api_url}{path}",
            {"campaign": {"status": "active"}, "iterations": []},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!status", "session_id": "session-123"})
    assert response.status_code == 200
    assert calls[0][0] == "/research-sessions/session-123/context"
    assert response.json()["command"] == "status"


def test_compare_command_returns_helpful_text_without_campaign() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (f"{settings.workflow_api_url}{path}", {"session": {"session_id": "session-123"}})
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="autoresearch campaign not found")

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!compare"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "compare"
    assert "No autoresearch campaign yet" in payload["response_text"]


def test_next_command_bootstraps_campaign_and_launches_batch() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (f"{settings.workflow_api_url}{path}", {"session": {"session_id": "session-123"}})
        if path.endswith("/autoresearch-summary"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="autoresearch campaign not found")
        if path.endswith("/draft-methodologies"):
            return (f"{settings.workflow_api_url}{path}", {"methodology_drafts": [{}, {}, {}]})
        if path.endswith("/launch-autoresearch-batch"):
            return (f"{settings.workflow_api_url}{path}", {"launches": [{}, {}]})
        raise AssertionError(path)

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!next"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "next"
    assert "Started autoresearch, drafted 3 variant(s), and launched 2 iteration(s)." == payload["response_text"]


def test_next_command_decides_and_launches_when_campaign_exists() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (f"{settings.workflow_api_url}{path}", {"session": {"session_id": "session-123"}})
        if path.endswith("/autoresearch-summary"):
            return (f"{settings.workflow_api_url}{path}", {"campaign": {"campaign_id": "camp-123"}})
        if path.endswith("/decide-autoresearch-batch"):
            return (f"{settings.workflow_api_url}{path}", {"decisions": [{}, {}]})
        if path.endswith("/launch-autoresearch-batch"):
            return (f"{settings.workflow_api_url}{path}", {"launches": [{}]})
        raise AssertionError(path)

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!next"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "next"
    assert "Recorded 2 completed decision(s) and launched 1 next iteration(s)." == payload["response_text"]


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


def test_launch_batch_resolves_session_before_transition() -> None:
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
            {"launches": [{"iteration": {"iteration_id": "iter-1"}}, {"iteration": {"iteration_id": "iter-2"}}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!launch-batch"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "launch-batch"
    assert calls[0][0] == "/research-sessions/latest/context"
    assert calls[1][0] == "/research-sessions/session-123/transitions/launch-autoresearch-batch"
    assert "Launched 2 autoresearch iteration(s)" in payload["response_text"]


def test_decide_batch_resolves_session_before_transition() -> None:
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
            {"decisions": [{"decision_type": "keep"}, {"decision_type": "discard"}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!decide-batch"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "decide-batch"
    assert calls[0][0] == "/research-sessions/latest/context"
    assert calls[1][0] == "/research-sessions/session-123/transitions/decide-autoresearch-batch"
    assert "Recorded 2 autoresearch decision(s)" in payload["response_text"]


def test_non_command_turns_forward_to_openclaw() -> None:
    client = TestClient(create_app(settings=Settings(), requester=lambda *args, **kwargs: ("", {})))
    response = client.post("/dispatch", json={"message": "what do you think of this paper?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is False
    assert payload["forward_to_openclaw"] is True
