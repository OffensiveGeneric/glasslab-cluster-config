from fastapi.testclient import TestClient

from app.main import Settings, create_app


def _client(requester):
    return TestClient(create_app(settings=Settings(), requester=requester))


def test_help_command_returns_supported_surface_only() -> None:
    client = _client(lambda *args, **kwargs: ("", {}))
    response = client.post("/dispatch", json={"message": "!help"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is True
    assert payload["command"] == "help"
    assert "!new <goal>" in payload["response_text"]
    assert "!decide <keep|discard|revise>" in payload["response_text"]
    assert "Use !help legacy" not in payload["response_text"]
    assert "legacy/debug" not in payload["response_text"]


def test_unsupported_bang_command_returns_deterministic_rejection() -> None:
    client = _client(lambda *args, **kwargs: ("", {}))
    response = client.post("/dispatch", json={"message": "!research something old"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is False
    assert "deterministic Glasslab commands" in payload["response_text"]


def test_non_command_turn_returns_deterministic_rejection() -> None:
    client = _client(lambda *args, **kwargs: ("", {}))
    response = client.post("/dispatch", json={"message": "what do you think?"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is False
    assert "Use !help" in payload["response_text"]


def test_new_command_creates_session() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return f"{settings.workflow_api_url}{path}", {
            "session_id": "session-123",
            "title": "Artist Similarity",
        }

    client = _client(fake_requester)
    response = client.post("/dispatch", json={"message": "!new artist similarity metric learning"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "new"
    assert calls == [
        (
            "/research-sessions",
            "POST",
            {
                "goal_statement": "artist similarity metric learning",
                "priorities": [],
                "submitted_by": "research-command-router",
            },
        )
    ]


def test_add_command_routes_dataset_intake() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return f"{settings.workflow_api_url}{path}", {
            "record_type": "dataset",
            "dataset": {"name": "WikiArt", "uri": "https://example.org/wikiart.csv"},
            "current_plan_status": "needs_plan",
        }

    client = _client(fake_requester)
    response = client.post("/dispatch", json={"message": "!add dataset: https://example.org/wikiart.csv"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add"
    assert calls[0][0] == "/research-sessions/latest/intake"
    assert calls[0][2]["dataset_uri"] == "https://example.org/wikiart.csv"
    assert "Current plan status: needs_plan." in payload["response_text"]


def test_plan_check_run_and_decide_dispatch_to_single_backend_endpoints() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        payloads = {
            "/research-sessions/latest/transitions/prepare-current-plan": {
                "design_id": "design-1",
                "workflow_id": "artist-similarity",
                "status": "prepared",
            },
            "/research-sessions/latest/preflight/current-plan": {
                "workflow_id": "artist-similarity",
                "blocking_issues": [],
                "warnings": ["warn"],
            },
            "/research-sessions/latest/transitions/run-happy-path": {
                "run": {"run_id": "run-1", "workflow_id": "artist-similarity"}
            },
            "/research-sessions/latest/decisions/current": {
                "decision": "keep"
            },
        }
        return f"{settings.workflow_api_url}{path}", payloads[path]

    client = _client(fake_requester)

    assert client.post("/dispatch", json={"message": "!plan"}).status_code == 200
    assert client.post("/dispatch", json={"message": "!check"}).status_code == 200
    assert client.post("/dispatch", json={"message": "!run"}).status_code == 200
    assert client.post("/dispatch", json={"message": "!decide keep looks good"}).status_code == 200

    assert calls == [
        ("/research-sessions/latest/transitions/prepare-current-plan", "POST", None),
        ("/research-sessions/latest/preflight/current-plan", "GET", None),
        ("/research-sessions/latest/transitions/run-happy-path", "POST", None),
        (
            "/research-sessions/latest/decisions/current",
            "POST",
            {
                "decision": "keep",
                "note": "looks good",
                "submitted_by": "research-command-router",
            },
        ),
    ]


def test_compare_missing_campaign_returns_compact_message() -> None:
    from fastapi import HTTPException, status

    def fake_requester(settings, path, method="GET", body=None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No autoresearch campaign yet")

    client = _client(fake_requester)
    response = client.post("/dispatch", json={"message": "!compare"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is True
    assert payload["command"] == "compare"
    assert "No autoresearch campaign yet" in payload["response_text"]


def test_next_routes_to_single_advance_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return f"{settings.workflow_api_url}{path}", {
            "drafted_methodology_count": 2,
            "decisions_recorded": 1,
            "launches_started": 1,
        }

    client = _client(fake_requester)
    response = client.post("/dispatch", json={"message": "!next"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "next"
    assert calls == [
        ("/research-sessions/latest/transitions/advance-autoresearch", "POST", None)
    ]
