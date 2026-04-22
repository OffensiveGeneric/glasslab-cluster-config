from fastapi.testclient import TestClient

from app.main import Settings, create_app


def test_help_command_returns_local_text() -> None:
    client = TestClient(create_app(settings=Settings(), requester=lambda *args, **kwargs: ("", {})))
    response = client.post("/dispatch", json={"message": "!help"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is True
    assert payload["forward_to_openclaw"] is False
    assert "session = one research workspace" in payload["response_text"]
    assert "campaign = the autoresearch loop inside a session" in payload["response_text"]
    assert "!new <goal>" in payload["response_text"]
    assert "!add <thing>" in payload["response_text"]
    assert "!plan" in payload["response_text"]
    assert "!check" in payload["response_text"]
    assert "!decide <keep|discard|revise>" in payload["response_text"]
    assert "Use !help legacy" in payload["response_text"]
    assert "Legacy/debug commands still supported:" not in payload["response_text"]
    assert "!next-paper" not in payload["response_text"]


def test_help_legacy_command_returns_compatibility_surface() -> None:
    client = TestClient(create_app(settings=Settings(), requester=lambda *args, **kwargs: ("", {})))
    response = client.post("/dispatch", json={"message": "!help legacy"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matched"] is True
    assert payload["forward_to_openclaw"] is False
    assert "Legacy/debug commands still supported:" in payload["response_text"]
    assert "!next-paper" in payload["response_text"]
    assert "!decide-latest" in payload["response_text"]


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
    assert "Started internet-backed literature search" in payload["response_text"]
    assert len(calls) == 1


def test_search_command_alias_calls_start_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        assert path == "/research-sessions/start-literature-search"
        assert method == "POST"
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "session": {"title": "Artist Similarity"},
                "paper_intake_queue": {"candidates": [{"paper_id": "a"}], "coverage_summary": {"mode": "external"}},
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!search artist similarity metric learning"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "search"
    assert "Started internet-backed literature search" in payload["response_text"]
    assert len(calls) == 1


def test_start_command_alias_creates_session() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        assert path == "/research-sessions"
        assert method == "POST"
        return (
            f"{settings.workflow_api_url}{path}",
            {"session_id": "session-123", "title": "Artist Similarity"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!start artist similarity metric learning"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "new"
    assert "Created research session" in payload["response_text"]
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
    assert payload["command"] == "new"
    assert "Created research session" in payload["response_text"]
    assert calls[0][0] == "/research-sessions"


def test_add_command_routes_to_generic_intake_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"record_type": "dataset", "dataset": {"name": "WikiArt", "uri": "https://www.wikiart.org/"}, "current_plan_status": "needs_plan"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add dataset: https://www.wikiart.org/"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add"
    assert calls[0][0] == "/research-sessions/latest/intake"
    assert calls[0][2]["dataset_uri"] == "https://www.wikiart.org/"


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
            {"title": "source.pdf"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add-pdf https://example.org/paper.pdf"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add-pdf"
    assert calls[0][0] == "/research-sessions/latest/source-documents/ingest"
    assert calls[0][2]["source_url"] == "https://example.org/paper.pdf"


def test_add_url_routes_to_manual_queue_with_official_page() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"title": "source.html"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add-url https://example.org/paper-page.html"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add-url"
    assert calls[0][0] == "/research-sessions/latest/source-documents/ingest"
    assert calls[0][2]["source_url"] == "https://example.org/paper-page.html"


def test_add_url_sanitizes_garbage_source_title() -> None:
    def fake_requester(settings, path, method="GET", body=None):
        return (
            f"{settings.workflow_api_url}{path}",
            {"title": "@import url('https://fonts.example/css'); body { color: red; }"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add-url https://dreamsim-nights.github.io/"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add-url"
    assert "dreamsim-nights.github.io" in payload["response_text"]
    assert "@import" not in payload["response_text"]


def test_add_dataset_routes_to_session_dataset_creation() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"dataset_id": "dataset-123", "name": "WikiArt", "uri": "https://www.wikiart.org/"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!add-dataset https://www.wikiart.org/"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "add-dataset"
    assert calls[0][0] == "/research-sessions/latest/datasets"
    assert calls[0][2]["uri"] == "https://www.wikiart.org/"


def test_datasets_lists_attached_datasets() -> None:
    def fake_requester(settings, path, method="GET", body=None):
        assert path == "/research-sessions/latest/datasets"
        return (
            f"{settings.workflow_api_url}{path}",
            [
                {"dataset_id": "dataset-1", "name": "Met Open Access", "uri": "https://metmuseum.github.io/"},
                {"dataset_id": "dataset-2", "name": "WikiArt", "uri": "https://www.wikiart.org/"},
            ],
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!datasets"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "datasets"
    assert "dataset-1: Met Open Access" in payload["response_text"]
    assert "dataset-2: WikiArt" in payload["response_text"]


def test_use_dataset_attaches_existing_dataset() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"dataset_id": "dataset-123", "name": "Met Open Access"},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!use-dataset dataset-123"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "use-dataset"
    assert calls[0][0] == "/research-sessions/latest/datasets/attach"
    assert calls[0][2]["dataset_id"] == "dataset-123"


def test_add_pdf_uses_pinned_session_when_provided() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"title": "source.pdf"},
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
    assert calls[0][0] == "/research-sessions/session-123/source-documents/ingest"


def test_next_paper_uses_pinned_session_when_provided() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"normalized_summary": "Pinned-session staged paper summary."},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post(
        "/dispatch",
        json={
            "message": "!next-paper",
            "session_id": "session-123",
        },
    )
    assert response.status_code == 200
    assert response.json()["command"] == "next-paper"
    assert calls[0][0] == "/research-sessions/session-123/paper-intake-queues/stage-next-intake"


def test_run_command_routes_to_session_run_creation() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "session": {"session_id": "session-123"},
                "design": {"design_id": "design-123"},
                "run": {"run_id": "run-123", "workflow_id": "gpu-experiment"},
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!run"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "run"
    assert calls == [
        ("/research-sessions/latest/transitions/run-happy-path", "POST", None),
    ]


def test_run_command_uses_pinned_session_alias() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "session": {"session_id": "session-123"},
                "design": {"design_id": "design-123"},
                "run": {"run_id": "run-123", "workflow_id": "gpu-experiment"},
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!run", "session_id": "session-123"})
    assert response.status_code == 200
    assert calls == [
        ("/research-sessions/session-123/transitions/run-happy-path", "POST", None),
    ]


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


def test_check_command_reads_current_plan_preflight() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"workflow_id": "gpu-experiment", "blocking_issues": [], "warnings": ["ok"]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!check"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "check"
    assert calls == [
        ("/research-sessions/latest/preflight/current-plan", "GET", None),
    ]


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


def test_state_command_adds_campaign_summary_when_present() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {
                    "session": {"session_id": "session-123", "title": "DreamSim", "goal_statement": "replicate dreamsim"},
                    "paper_intake_queue": {"status": "ready", "candidates": [{"id": "a"}]},
                    "active_dataset": {"dataset_id": "dataset-1", "name": "WikiArt"},
                },
            )
        return (
            f"{settings.workflow_api_url}{path}",
            {"campaign": {"status": "active"}, "iterations": [{}, {}]},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!state"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "state"
    assert "Active dataset: WikiArt." in payload["response_text"]
    assert "Campaign status: active with 2 iteration(s)." in payload["response_text"]
    assert "Active session 'DreamSim'." in payload["response_text"]


def test_state_uses_pinned_session_context_when_provided() -> None:
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
    response = client.post("/dispatch", json={"message": "!state", "session_id": "session-123"})
    assert response.status_code == 200
    assert calls[0][0] == "/research-sessions/session-123/context"
    assert response.json()["command"] == "state"


def test_compare_command_returns_helpful_text_without_campaign() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="autoresearch campaign not found")

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!compare"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "compare"
    assert "No autoresearch campaign yet" in payload["response_text"]
    assert calls == [
        ("/research-sessions/latest/autoresearch-model-comparison", "GET", None),
    ]


def test_state_mentions_missing_campaign_when_none_exists() -> None:
    def fake_requester(settings, path, method="GET", body=None):
        if path == "/research-sessions/latest/context":
            return (
                f"{settings.workflow_api_url}{path}",
                {
                    "session": {"session_id": "session-123", "title": "Artist Similarity", "goal_statement": "learn an art metric"},
                    "paper_intake_queue": {"status": "ready", "candidates": []},
                },
            )
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="autoresearch campaign not found")

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!state"})
    assert response.status_code == 200
    payload = response.json()
    assert "No autoresearch campaign yet." in payload["response_text"]


def test_decide_command_routes_to_current_decision_endpoint() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {"operation": {"operation_id": "op-123"}},
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!decide keep use the DreamSim baseline"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "decide"
    assert calls == [
        (
            "/research-sessions/latest/decisions/current",
            "POST",
            {
                "decision": "keep",
                "note": "use the DreamSim baseline",
                "submitted_by": "research-command-router",
            },
        ),
    ]


def test_next_command_bootstraps_campaign_and_launches_batch() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "drafted_methodology_count": 3,
                "decisions_recorded": 0,
                "launches_started": 2,
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!next"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "next"
    assert (
        "Drafted 3 methodology variant(s), recorded 0 completed decision(s), and launched 2 next iteration(s)."
        == payload["response_text"]
    )
    assert calls == [
        ("/research-sessions/latest/transitions/advance-autoresearch", "POST", None),
    ]


def test_next_command_decides_and_launches_when_campaign_exists() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "drafted_methodology_count": 0,
                "decisions_recorded": 2,
                "launches_started": 1,
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!next"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "next"
    assert (
        "Drafted 0 methodology variant(s), recorded 2 completed decision(s), and launched 1 next iteration(s)."
        == payload["response_text"]
    )
    assert calls == [
        ("/research-sessions/latest/transitions/advance-autoresearch", "POST", None),
    ]


def test_next_command_uses_pinned_session_alias() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def fake_requester(settings, path, method="GET", body=None):
        calls.append((path, method, body))
        return (
            f"{settings.workflow_api_url}{path}",
            {
                "drafted_methodology_count": 0,
                "decisions_recorded": 1,
                "launches_started": 1,
            },
        )

    client = TestClient(create_app(settings=Settings(), requester=fake_requester))
    response = client.post("/dispatch", json={"message": "!next", "session_id": "session-123"})
    assert response.status_code == 200
    assert calls == [
        ("/research-sessions/session-123/transitions/advance-autoresearch", "POST", None),
    ]


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
