from pathlib import Path

from fastapi import HTTPException
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
    assert payload["chat_enabled"] is False


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


def test_inbound_accepts_explicit_session_id_hint(tmp_path: Path) -> None:
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
    payload = response.json()
    assert payload["response_text"] == "Created run 'run-123'."


def test_pdf_attachment_can_drive_add_pdf_without_text(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
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


def test_csv_attachment_can_drive_add_dataset_without_text(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!add-dataset https://example.org/train.csv"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Attached dataset.",
            "router_payload": {"command": "add-dataset"},
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
                        "url": "https://example.org/train.csv",
                        "mime_type": "text/csv",
                        "filename": "train.csv",
                    }
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["forwarded_message"] == "!add-dataset https://example.org/train.csv"
    finally:
        main_module._request_research_ingress = original


def test_add_dataset_command_is_augmented_by_csv_attachment(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert message == "!add-dataset https://example.org/train.csv"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Attached dataset.",
            "router_payload": {"command": "add-dataset"},
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
                "message": "!add-dataset",
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
        payload = response.json()
        assert payload["forwarded_message"] == "!add-dataset https://example.org/train.csv"
    finally:
        main_module._request_research_ingress = original


def test_add_pdf_command_is_augmented_by_pdf_attachment(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
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

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
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


def test_non_command_turn_can_use_chat_backend(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        return {
            "handled": False,
            "route": "openclaw-fallback",
            "response_text": "",
            "forward_to_openclaw": True,
        }

    def fake_chat(settings, *, messages, request):
        assert request.message == "what should we test next?"
        return "Try a stronger baseline and compare the split strategy."

    original_ingress = main_module._request_research_ingress
    original_chat = main_module._chat_reply
    main_module._request_research_ingress = fake_ingress
    main_module._chat_reply = fake_chat
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    chat_backend_url="http://example.test/api/chat",
                )
            )
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "what should we test next?",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original_ingress
        main_module._chat_reply = original_chat

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "gateway-chat"
    assert "stronger baseline" in payload["response_text"]
    assert payload["router_payload"] == {"chat_backend": True}


def test_dm_allowlist_blocks_unknown_sender(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                state_dir=str(tmp_path),
                dm_policy="allowlist",
                allow_from="+15555550123",
            )
        )
    )
    response = client.post(
        "/webhooks/whatsapp/inbound",
        json={
            "sender": "+15555550999",
            "message": "!status",
            "attachments": [],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is False
    assert payload["route"] == "gateway-policy"
    assert "approved Glasslab allowlist" in payload["response_text"]


def test_dm_allowlist_accepts_whatsapp_phone_jid(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert sender == "19145316570@s.whatsapp.net"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Session status is available.",
            "router_payload": {"command": "status"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    dm_policy="allowlist",
                    allow_from="+19145316570",
                )
            )
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "19145316570@s.whatsapp.net",
                "message": "!status",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "deterministic-router"


def test_owner_is_allowed_even_if_not_listed_in_allow_from(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        assert sender == "+15555550001"
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Session status is available.",
            "router_payload": {"command": "status"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    dm_policy="allowlist",
                    owner="+15555550001",
                    allow_from="+15555550002",
                )
            )
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550001",
                "message": "!status",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "deterministic-router"


def test_group_chat_can_use_chat_backend_when_allowlisted(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        return {
            "handled": False,
            "route": "openclaw-fallback",
            "response_text": "",
            "forward_to_openclaw": True,
        }

    def fake_chat(settings, *, messages, request):
        assert request.is_group is True
        assert request.conversation_id == "group-123"
        return "I can help in this approved group."

    original_ingress = main_module._request_research_ingress
    original_chat = main_module._chat_reply
    main_module._request_research_ingress = fake_ingress
    main_module._chat_reply = fake_chat
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    chat_backend_url="http://example.test/api/chat",
                    group_policy="allowlist",
                    allow_groups="group-123",
                )
            )
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "conversation_id": "group-123",
                "is_group": True,
                "message": "what happened in the last batch?",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original_ingress
        main_module._chat_reply = original_chat

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "gateway-chat"
    assert "approved group" in payload["response_text"]


def test_group_chat_can_use_chat_backend_when_member_is_allowlisted(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        return {
            "handled": False,
            "route": "openclaw-fallback",
            "response_text": "",
            "forward_to_openclaw": True,
        }

    def fake_chat(settings, *, messages, request):
        assert request.is_group is True
        assert request.conversation_id == "120363419610000000@g.us"
        assert request.sender == "16466376467@s.whatsapp.net"
        return "Group chat is enabled for approved members."

    original_ingress = main_module._request_research_ingress
    original_chat = main_module._chat_reply
    main_module._request_research_ingress = fake_ingress
    main_module._chat_reply = fake_chat
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    chat_backend_url="http://example.test/api/chat",
                    group_policy="member-allowlist",
                    allow_from="+16466376467",
                )
            )
        )
        response = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "16466376467@s.whatsapp.net",
                "conversation_id": "120363419610000000@g.us",
                "is_group": True,
                "message": "what happened in the last batch?",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original_ingress
        main_module._chat_reply = original_chat

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["route"] == "gateway-chat"
    assert "approved members" in payload["response_text"]


def test_duplicate_attachment_driven_add_is_suppressed(tmp_path: Path) -> None:
    import app.main as main_module

    calls: list[str] = []

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
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

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
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


def test_gateway_reuses_pinned_workflow_session_id(tmp_path: Path) -> None:
    import app.main as main_module

    observed_session_ids: list[str | None] = []

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        observed_session_ids.append(session_id)
        if message == "!new-session artist similarity":
            return {
                "handled": True,
                "route": "deterministic-router",
                "response_text": "Created research session.",
                "router_payload": {
                    "command": "new-session",
                    "payload": {"session_id": "session-123"},
                },
            }
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Scoped session status.",
            "router_payload": {"command": "status"},
        }

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        first = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "!new-session artist similarity",
                "attachments": [],
            },
        )
        second = client.post(
            "/webhooks/whatsapp/inbound",
            json={
                "sender": "+15555550123",
                "message": "!status",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert first.status_code == 200
    assert second.status_code == 200
    assert observed_session_ids == [None, "session-123"]


def test_deterministic_backend_error_is_returned_as_user_reply(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        raise HTTPException(
            status_code=409,
            detail="design method_spec is not ready_for_run: dataset_uri is unresolved",
        )

    original = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.post(
            "/webhooks/whatsapp/provider",
            json={
                "provider": "whatsapp",
                "provider_message_id": "wamid-error-1",
                "sender": "+15555550123",
                "text": "!run",
                "attachments": [],
            },
        )
    finally:
        main_module._request_research_ingress = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is False
    assert payload["route"] == "deterministic-router-error"
    assert "dataset_uri is unresolved" in payload["response_text"]
    assert payload["router_payload"]["backend_error"] is True


def test_meta_webhook_verification_succeeds(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                state_dir=str(tmp_path),
                meta_verify_token="verify-me",
            )
        )
    )
    response = client.get(
        "/webhooks/meta/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.text == "12345"


def test_meta_webhook_text_message_is_normalized_and_replied(tmp_path: Path) -> None:
    import app.main as main_module

    observed_messages: list[str] = []
    outbound_messages: list[tuple[str, str]] = []

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        observed_messages.append(message)
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Current session status.",
            "router_payload": {"command": "status"},
        }

    def fake_send(settings, *, recipient, text):
        outbound_messages.append((recipient, text))
        return {"messages": [{"id": "wamid-out-1"}]}

    original_ingress = main_module._request_research_ingress
    original_send = main_module._send_meta_text_reply
    main_module._request_research_ingress = fake_ingress
    main_module._send_meta_text_reply = fake_send
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    meta_access_token="token",
                    meta_phone_number_id="123",
                )
            )
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15555550123",
                                        "id": "wamid-meta-1",
                                        "type": "text",
                                        "text": {"body": "!status"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        response = client.post("/webhooks/meta/whatsapp", json=payload)
    finally:
        main_module._request_research_ingress = original_ingress
        main_module._send_meta_text_reply = original_send

    assert response.status_code == 200
    body = response.json()
    assert body["processed_messages"] == 1
    assert observed_messages == ["!status"]
    assert outbound_messages == [("15555550123", "Current session status.")]
    assert body["results"][0]["reply_sent"] is True


def test_meta_document_message_becomes_gateway_attachment_url(tmp_path: Path) -> None:
    import app.main as main_module

    observed_messages: list[str] = []

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        observed_messages.append(message)
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Added PDF candidate.",
            "router_payload": {"command": "add-pdf"},
        }

    original_ingress = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    gateway_base_url="http://gateway.test",
                )
            )
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15555550123",
                                        "id": "wamid-meta-doc-1",
                                        "type": "document",
                                        "document": {
                                            "id": "meta-media-123",
                                            "mime_type": "application/pdf",
                                            "filename": "paper.pdf",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        response = client.post("/webhooks/meta/whatsapp", json=payload)
    finally:
        main_module._request_research_ingress = original_ingress

    assert response.status_code == 200
    assert observed_messages == [
        "!add-pdf http://gateway.test/attachments/meta/meta-media-123"
    ]


def test_meta_csv_document_message_becomes_dataset_attachment_url(tmp_path: Path) -> None:
    import app.main as main_module

    observed_messages: list[str] = []

    def fake_ingress(settings, *, message, sender, channel, session_id=None):
        observed_messages.append(message)
        return {
            "handled": True,
            "route": "deterministic-router",
            "response_text": "Attached dataset.",
            "router_payload": {"command": "add-dataset"},
        }

    original_ingress = main_module._request_research_ingress
    main_module._request_research_ingress = fake_ingress
    try:
        client = TestClient(
            create_app(
                settings=Settings(
                    state_dir=str(tmp_path),
                    gateway_base_url="http://gateway.test",
                )
            )
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15555550123",
                                        "id": "wamid-meta-csv-1",
                                        "type": "document",
                                        "document": {
                                            "id": "meta-media-csv-123",
                                            "mime_type": "text/csv",
                                            "filename": "train.csv",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        response = client.post("/webhooks/meta/whatsapp", json=payload)
    finally:
        main_module._request_research_ingress = original_ingress

    assert response.status_code == 200
    assert observed_messages == [
        "!add-dataset http://gateway.test/attachments/meta/meta-media-csv-123"
    ]


def test_meta_attachment_proxy_uses_media_fetcher(tmp_path: Path) -> None:
    import app.main as main_module

    def fake_fetch(settings, media_id):
        assert media_id == "meta-media-123"
        return (b"pdf-bytes", "application/pdf", "paper.pdf")

    original_fetch = main_module._fetch_meta_media_content
    main_module._fetch_meta_media_content = fake_fetch
    try:
        client = TestClient(create_app(settings=Settings(state_dir=str(tmp_path))))
        response = client.get("/attachments/meta/meta-media-123")
    finally:
        main_module._fetch_meta_media_content = original_fetch

    assert response.status_code == 200
    assert response.content == b"pdf-bytes"
    assert response.headers["content-type"].startswith("application/pdf")
