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


def test_forwards_explicit_command_and_persists_session(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel):
        assert message == "!run"
        assert sender == "+15555550123"
        assert channel == "whatsapp"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Created run 'run-123'.",
            "router_payload": {"command": "run"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(settings=Settings(state_dir=str(tmp_path)))
        )
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


def test_pdf_attachment_can_drive_add_pdf_without_text(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel):
        assert message == "!add-pdf https://example.org/paper.pdf"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Added PDF candidate.",
            "router_payload": {"command": "add-pdf"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(settings=Settings(state_dir=str(tmp_path)))
        )
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
        payload = response.json()
        assert payload["forwarded_message"] == "!add-pdf https://example.org/paper.pdf"
    finally:
        main_module._request_research_ingress = original


def test_add_pdf_command_is_augmented_by_pdf_attachment(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel):
        assert message == "!add-pdf https://example.org/paper.pdf"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Added PDF candidate.",
            "router_payload": {"command": "add-pdf"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(settings=Settings(state_dir=str(tmp_path)))
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "!add-pdf",
                "attachments": [
                    {
                        "url": "https://example.org/paper.pdf",
                        "mime_type": "application/pdf",
                    }
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["forwarded_message"] == "!add-pdf https://example.org/paper.pdf"
    finally:
        main_module._request_research_ingress = original


def test_empty_non_pdf_turn_is_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
    response = client.post(
        "/webhooks/whatsapp/inbound",
        json={
            "sender": "+15555550123",
            "message": "",
            "attachments": [
                {
                    "url": "https://example.org/image.jpg",
                    "mime_type": "image/jpeg",
                }
            ],
        },
    )
    assert response.status_code == 400


def test_non_command_turn_returns_gateway_owned_message(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel):
        return {
            "handled": False,
            "route": "openclaw-fallback",
            "response_text": "This turn should be forwarded to OpenClaw for free-form handling.",
            "forward_to_openclaw": True,
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(settings=Settings(state_dir=str(tmp_path)))
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "what do you think about this paper?",
                "attachments": [],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["handled"] is False
        assert payload["route"] == "openclaw-fallback"
        assert "Free-form chat is not enabled" in payload["response_text"]
    finally:
        main_module._request_research_ingress = original


def test_duplicate_attachment_driven_add_is_suppressed(tmp_path: Path) -> None:
    import app.main as main_module

    calls: list[str] = []

    def fake_ingress(settings, *, message, sender, channel):
        calls.append(message)
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Added PDF candidate.",
            "router_payload": {"command": "add-pdf"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        payload = {
            "sender": "+15555550123",
            "message": "",
            "attachments": [
                {
                    "url": "https://example.org/paper.pdf",
                    "mime_type": "application/pdf",
                    "filename": "paper.pdf",
                }
            ],
        }
        first = client.post("/webhooks/whatsapp/inbound", json=payload)
        second = client.post("/webhooks/whatsapp/inbound", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["response_text"] == "Added PDF candidate."
        assert second.json()["response_text"] == "Added PDF candidate."
        assert second.json()["router_payload"] == {"duplicate_suppressed": True}
        assert calls == ["!add-pdf https://example.org/paper.pdf"]
    finally:
        main_module._request_research_ingress = original


def test_provider_message_id_duplicate_is_suppressed(tmp_path: Path) -> None:
    import app.main as main_module

    calls: list[str] = []

    def fake_ingress(settings, *, message, sender, channel):
        calls.append(message)
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Created research session.",
            "router_payload": {"command": "new-session"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        payload = {
            "provider": "whatsapp",
            "provider_message_id": "wamid-123",
            "sender": "+15555550123",
            "text": "!new-session provider dedupe test",
            "attachments": [],
        }
        first = client.post("/webhooks/whatsapp/provider", json=payload)
        second = client.post("/webhooks/whatsapp/provider", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert calls == ["!new-session provider dedupe test"]
        assert second.json()["router_payload"]["duplicate_scope"] == "provider_message_id"
        transcript = client.get("/sessions/whatsapp/+15555550123")
        assert transcript.status_code == 200
        messages = transcript.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["provider_message_id"] == "wamid-123"
    finally:
        main_module._request_research_ingress = original
