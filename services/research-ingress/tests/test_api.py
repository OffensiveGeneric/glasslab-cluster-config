from fastapi.testclient import TestClient

from app.main import Settings, create_app


def test_healthz_reports_router_url() -> None:
    client = TestClient(create_app(settings=Settings()))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert "command_router_url" in response.json()


def test_inbound_handles_deterministic_command() -> None:
    def fake_router(settings, message, submitted_by):
        assert message.startswith("!research")
        assert submitted_by == "whatsapp:+15555550123"
        return {
            "matched": True,
            "response_text": "Started literature search.",
            "command": "research",
        }

    app = create_app(settings=Settings())
    app.dependency_overrides = {}
    app.router.routes.clear()  # not used; keep factory-style tests simple

    from app.main import InboundMessageRequest, InboundMessageResponse, FastAPI

    # rebuild app with a monkeypatched module-level helper
    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!research forged art detection with computer vision methods",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["forward_to_openclaw"] is False
    assert payload["route"] == "deterministic-router"


def test_inbound_marks_non_command_turn_for_openclaw() -> None:
    def fake_router(settings, message, submitted_by):
        return {
            "matched": False,
            "forward_to_openclaw": True,
            "response_text": "No deterministic command matched.",
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
    assert payload["handled"] is False
    assert payload["forward_to_openclaw"] is True
    assert payload["route"] == "openclaw-fallback"


def test_inbound_handles_add_paper_command() -> None:
    def fake_router(settings, message, submitted_by):
        assert message.startswith("!add-paper")
        assert submitted_by == "whatsapp:+15555550123"
        return {
            "matched": True,
            "response_text": "Added manual paper candidate 'Manual paper candidate' to the current queue.",
            "command": "add-paper",
            "workflow_api_endpoint": "http://workflow-api/research-sessions/latest/paper-intake-queue/manual-paper",
            "payload": {"candidates": [{"title": "Manual paper candidate"}]},
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!add-paper https://arxiv.org/abs/2401.12345",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["forward_to_openclaw"] is False
    assert payload["route"] == "deterministic-router"
    assert payload["router_payload"]["command"] == "add-paper"


def test_inbound_handles_add_pdf_command() -> None:
    def fake_router(settings, message, submitted_by):
        assert message.startswith("!add-pdf")
        assert submitted_by == "whatsapp:+15555550123"
        return {
            "matched": True,
            "response_text": "Added PDF candidate 'Manual PDF candidate' to the current queue.",
            "command": "add-pdf",
            "workflow_api_endpoint": "http://workflow-api/research-sessions/latest/paper-intake-queue/manual-paper",
            "payload": {"candidates": [{"title": "Manual PDF candidate"}]},
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!add-pdf https://example.org/paper.pdf",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["forward_to_openclaw"] is False
    assert payload["route"] == "deterministic-router"
    assert payload["router_payload"]["command"] == "add-pdf"


def test_inbound_handles_run_command() -> None:
    def fake_router(settings, message, submitted_by):
        assert message == "!run"
        assert submitted_by == "whatsapp:+15555550123"
        return {
            "matched": True,
            "response_text": "Created run 'run-123' for workflow 'gpu-experiment'.",
            "command": "run",
            "workflow_api_endpoint": "http://workflow-api/research-sessions/latest/runs/from-design",
            "payload": {"run_id": "run-123", "workflow_id": "gpu-experiment"},
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
    assert payload["forward_to_openclaw"] is False
    assert payload["route"] == "deterministic-router"
    assert payload["router_payload"]["command"] == "run"


def test_inbound_handles_launch_batch_command() -> None:
    def fake_router(settings, message, submitted_by):
        assert message == "!launch-batch"
        assert submitted_by == "whatsapp:+15555550123"
        return {
            "matched": True,
            "response_text": "Launched 2 autoresearch iteration(s) for the active campaign.",
            "command": "launch-batch",
            "workflow_api_endpoint": "http://workflow-api/research-sessions/latest/transitions/launch-autoresearch-batch",
            "payload": {"launches": [{}, {}]},
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!launch-batch",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["forward_to_openclaw"] is False
    assert payload["route"] == "deterministic-router"
    assert payload["router_payload"]["command"] == "launch-batch"


def test_inbound_handles_decide_batch_command() -> None:
    def fake_router(settings, message, submitted_by):
        assert message == "!decide-batch"
        assert submitted_by == "whatsapp:+15555550123"
        return {
            "matched": True,
            "response_text": "Recorded 2 autoresearch decision(s) for ready completed iterations.",
            "command": "decide-batch",
            "workflow_api_endpoint": "http://workflow-api/research-sessions/latest/transitions/decide-autoresearch-batch",
            "payload": {"decisions": [{}, {}]},
        }

    import app.main as main_module

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!decide-batch",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["forward_to_openclaw"] is False
    assert payload["route"] == "deterministic-router"
    assert payload["router_payload"]["command"] == "decide-batch"


def test_inbound_surfaces_router_timeout_as_gateway_timeout() -> None:
    import app.main as main_module

    def fake_router(settings, message, submitted_by):
        raise main_module.HTTPException(status_code=504, detail="research-command-router timed out")

    original = main_module._request_router
    main_module._request_router = fake_router
    try:
        client = TestClient(create_app(settings=Settings()))
        response = client.post(
            "/inbound",
            json={
                "message": "!interpret",
                "sender": "+15555550123",
                "channel": "whatsapp",
            },
        )
    finally:
        main_module._request_router = original

    assert response.status_code == 504
    assert response.json()["detail"] == "research-command-router timed out"
