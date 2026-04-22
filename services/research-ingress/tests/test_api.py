from fastapi.testclient import TestClient

from app.main import Settings, create_app


def test_healthz_reports_router_url() -> None:
    client = TestClient(create_app(settings=Settings()))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert "command_router_url" in response.json()


def test_inbound_handles_deterministic_command() -> None:
    def fake_router(settings, message, submitted_by, session_id=None):
        assert message == "!run"
        assert submitted_by == "whatsapp:+15555550123"
        assert session_id is None
        return {
            "matched": True,
            "response_text": "Created run 'run-123'.",
            "command": "run",
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!run",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "deterministic-router"


def test_inbound_returns_deterministic_unsupported_turn_response() -> None:
    def fake_router(settings, message, submitted_by, session_id=None):
        return {
            "matched": False,
            "response_text": "This surface only supports deterministic Glasslab commands. Use !help for the supported command surface.",
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "what do you think about this paper?",
                "sender": "+15555550123",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "unsupported-turn"
    assert "Use !help" in payload["response_text"]


def test_inbound_passes_session_id_hint() -> None:
    def fake_router(settings, message, submitted_by, session_id=None):
        assert session_id == "session-123"
        return {
            "matched": True,
            "response_text": "Current session is ready.",
            "command": "state",
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!state",
                "sender": "+15555550123",
                "session_id": "session-123",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    assert response.json()["route"] == "deterministic-router"
