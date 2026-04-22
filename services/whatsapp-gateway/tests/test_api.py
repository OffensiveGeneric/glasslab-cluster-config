from pathlib import Path

from fastapi.testclient import TestClient

from app.main import Settings, create_app


def test_healthz_reports_ingress_url(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                research_ingress_url="http://example.test",
                state_dir=str(tmp_path),
            )
        )
    )
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["research_ingress_url"] == "http://example.test"
    assert "chat_enabled" not in payload


def test_forwards_explicit_command_and_persists_session(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!run"
        assert sender == "+15555550123"
        assert channel == "whatsapp"
        assert session_id is None
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Created run 'run-123'.",
            "router_payload": {"command": "run"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "channel": "whatsapp",
                "message": "!run",
                "attachments": [],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["forwarded_message"] == "!run"
        session = client.get("/sessions/whatsapp/+15555550123")
        assert session.status_code == 200
        messages = session.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
    finally:
        main_module._request_research_ingress = original


def test_explicit_session_id_hint_is_forwarded(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!run"
        assert session_id == "session-123"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Created run 'run-123'.",
            "router_payload": {"command": "run"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "channel": "whatsapp",
                "message": "!run",
                "session_id": "session-123",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert response.status_code == 200
    assert response.json()["response_text"] == "Created run 'run-123'."


def test_pdf_attachment_maps_to_generic_add_command(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!add https://example.org/paper.pdf"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Attached source.",
            "router_payload": {"command": "add"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "",
                "attachments": [
                    {
                        "url": "https://example.org/paper.pdf",
                        "mime_type": "application/pdf",
                        "filename": "paper.pdf",
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["forwarded_message"] == "!add https://example.org/paper.pdf"
    finally:
        main_module._request_research_ingress = original


def test_csv_attachment_maps_to_generic_add_dataset_command(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!add dataset: https://example.org/train.csv"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Attached dataset.",
            "router_payload": {"command": "add"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "",
                "attachments": [
                    {
                        "url": "https://example.org/train.csv",
                        "mime_type": "text/csv",
                        "filename": "train.csv",
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["forwarded_message"] == "!add dataset: https://example.org/train.csv"
    finally:
        main_module._request_research_ingress = original


def test_non_command_turn_returns_deterministic_rejection(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        return {
            "handled": True,
            "route": "unsupported-turn",
            "response_text": "This surface only supports deterministic Glasslab commands. Use !help for the supported command surface.",
            "router_payload": {"matched": False},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "what do you think about this paper?",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "unsupported-turn"
    assert "Use !help" in payload["response_text"]


def test_provider_webhook_pdf_attachment_is_normalized(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!add http://gateway.test/attachments/meta/meta-doc-123"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Attached source.",
            "router_payload": {"command": "add"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    gateway_base_url="http://gateway.test",
                    meta_access_token="token",
                    meta_phone_number_id="phone-id",
                )
            )
        )
        response = client.post(
            "/webhooks/whatsapp/provider",
            json={
                "provider": "whatsapp",
                "provider_message_id": "msg-123",
                "sender": "+15555550123",
                "text": "",
                "attachments": [
                    {
                        "url": "http://gateway.test/attachments/meta/meta-doc-123",
                        "mime_type": "application/pdf",
                        "filename": "paper.pdf",
                    }
                ],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert response.status_code == 200
    assert response.json()["forwarded_message"] == "!add http://gateway.test/attachments/meta/meta-doc-123"
