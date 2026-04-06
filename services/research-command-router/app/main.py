from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class Settings:
    workflow_api_url: str = os.environ.get(
        "GLASSLAB_RESEARCH_COMMAND_ROUTER_WORKFLOW_API_URL",
        "http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080",
    )
    timeout_seconds: int = int(
        os.environ.get("GLASSLAB_RESEARCH_COMMAND_ROUTER_TIMEOUT_SECONDS", "120")
    )
    default_submitted_by: str = os.environ.get(
        "GLASSLAB_RESEARCH_COMMAND_ROUTER_SUBMITTED_BY",
        "research-command-router",
    )


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    submitted_by: str | None = None
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("message must not be empty")
        return cleaned

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


class DispatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched: bool
    forward_to_openclaw: bool
    command: str | None = None
    response_text: str
    workflow_api_endpoint: str | None = None
    payload: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    workflow_api_url: str
    timeout_seconds: int


def _request_json(
    settings: Settings,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    endpoint = f"{settings.workflow_api_url.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(endpoint, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=settings.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return endpoint, payload
    except urllib_error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {"detail": exc.reason}
        raise HTTPException(status_code=exc.code, detail=detail.get("detail", detail))
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"workflow-api unreachable: {exc.reason}",
        )


def _parse_command(message: str) -> tuple[str, str] | None:
    text = message.strip()
    if not text:
        return None
    lowered = text.lower()
    prefixes = [
        ("!new-session", "new-session"),
        ("new-session:", "new-session"),
        ("!start", "start"),
        ("start:", "start"),
        ("!research", "research"),
        ("research:", "research"),
        ("!search", "search"),
        ("search:", "search"),
        ("!status", "status"),
        ("status:", "status"),
        ("!more-papers", "more-papers"),
        ("papers:", "more-papers"),
        ("!next-paper", "next-paper"),
        ("next-paper:", "next-paper"),
        ("!add-paper", "add-paper"),
        ("add-paper:", "add-paper"),
        ("!add-dataset", "add-dataset"),
        ("add-dataset:", "add-dataset"),
        ("!datasets", "datasets"),
        ("datasets:", "datasets"),
        ("!use-dataset", "use-dataset"),
        ("use-dataset:", "use-dataset"),
        ("!add-url", "add-url"),
        ("add-url:", "add-url"),
        ("!add-pdf", "add-pdf"),
        ("add-pdf:", "add-pdf"),
        ("!session", "session"),
        ("session:", "session"),
        ("!interpret", "interpret"),
        ("interpret:", "interpret"),
        ("!design", "design"),
        ("design:", "design"),
        ("!preflight", "preflight"),
        ("preflight:", "preflight"),
        ("!run", "run"),
        ("run:", "run"),
        ("!start-autoresearch", "start-autoresearch"),
        ("start-autoresearch:", "start-autoresearch"),
        ("!draft-methodologies", "draft-methodologies"),
        ("draft-methodologies:", "draft-methodologies"),
        ("!draft-notebook", "draft-notebook"),
        ("draft-notebook:", "draft-notebook"),
        ("!refine-notebook", "refine-notebook"),
        ("refine-notebook:", "refine-notebook"),
        ("!launch-iteration", "launch-iteration"),
        ("launch-iteration:", "launch-iteration"),
        ("!launch-batch", "launch-batch"),
        ("launch-batch:", "launch-batch"),
        ("!decide-batch", "decide-batch"),
        ("decide-batch:", "decide-batch"),
        ("!decide-latest", "decide-latest"),
        ("decide-latest:", "decide-latest"),
        ("!autoresearch", "autoresearch"),
        ("autoresearch:", "autoresearch"),
        ("!model-comparison", "model-comparison"),
        ("model-comparison:", "model-comparison"),
        ("!compare", "compare"),
        ("compare:", "compare"),
        ("!next", "next"),
        ("next:", "next"),
        ("!note", "note"),
        ("note:", "note"),
        ("!op", "op"),
        ("op:", "op"),
        ("!help", "help"),
        ("help:", "help"),
    ]
    for raw_prefix, command in prefixes:
        if lowered == raw_prefix:
            return command, ""
        if lowered.startswith(f"{raw_prefix} "):
            return command, text[len(raw_prefix) :].strip()
        if raw_prefix.endswith(":") and lowered.startswith(raw_prefix):
            return command, text[len(raw_prefix) :].strip()
    return None


def _help_text() -> str:
    return "\n".join(
        [
            "Glasslab runner flow:",
            "1. !new-session <goal> creates a blank workspace without literature search.",
            "2. !add-pdf [url] ingests a PDF source into the active workspace.",
            "   !add-url <url> ingests a webpage source into the active workspace.",
            "3. !add-dataset <uri> registers and attaches a dataset to the active workspace.",
            "   !datasets lists attached datasets. !use-dataset <id> switches the active one.",
            "4. !run prepares interpretation/design and launches the first bounded run.",
            "5. !next advances the active autoresearch campaign by deciding finished runs and launching the next batch.",
            "6. !compare summarizes the active campaign and best current method.",
            "7. !status shows the current workspace, active dataset, and campaign state.",
            "",
            "Core commands:",
            "!new-session <goal>",
            "!add-pdf [url]",
            "!add-url <url>",
            "!add-dataset <uri>",
            "!datasets",
            "!use-dataset <dataset_id>",
            "!start <topic>",
            "!search <topic>",
            "!run",
            "!next",
            "!compare",
            "!status",
            "",
            "Terms:",
            "session = one research workspace for one problem",
            "campaign = the autoresearch loop inside a session",
            "iteration = one candidate method/run inside a campaign",
            "",
            "Use !start or !search when you want internet/paper search.",
            "Use !new-session + !add-pdf or !add-url when you already have the source.",
            "Use !add-dataset before !run when the experiment needs an explicit dataset.",
            "",
            "Legacy/debug commands still available:",
            "!research !search !more-papers !add-paper !session !interpret !design !preflight",
            "!start-autoresearch !draft-methodologies !draft-notebook !refine-notebook",
            "!launch-iteration !launch-batch !decide-batch !decide-latest !autoresearch !model-comparison",
            "!note <text>",
            "!op",
            "!help",
        ]
    )


def _get_latest_session_id(
    settings: Settings,
    requester: Callable[..., tuple[str, dict[str, Any]]],
    session_id: str | None = None,
) -> tuple[str, dict[str, Any], str]:
    path = (
        f"/research-sessions/{session_id}/context"
        if session_id
        else "/research-sessions/latest/context"
    )
    endpoint, payload = requester(settings, path)
    session = payload.get("session") or {}
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="research session not found",
        )
    return endpoint, payload, session_id


def _summarize_queue(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    coverage = payload.get("coverage_summary") or {}
    mode = coverage.get("mode") or coverage.get("provider") or "queue"
    return (
        f"Queue ready with {len(candidates)} candidate paper(s). "
        f"Coverage mode: {mode}."
    )


def _http_detail_text(exc: HTTPException) -> str:
    if isinstance(exc.detail, str):
        return exc.detail
    return json.dumps(exc.detail, sort_keys=True)


def _safe_source_label(title: str | None, source_url: str, fallback: str) -> str:
    cleaned = " ".join(str(title or "").split()).strip()
    suspicious_markers = ("@import", "{", "}", ";", "function(", "var ", "const ")
    if cleaned and len(cleaned) <= 120 and not any(marker in cleaned.lower() for marker in suspicious_markers):
        return cleaned
    parsed = urlparse(source_url)
    host = parsed.netloc or fallback
    path_tail = parsed.path.rstrip("/").rsplit("/", 1)[-1] if parsed.path else ""
    if path_tail and path_tail not in {"", "/"}:
        return f"{host}/{path_tail}"[:120]
    return host[:120] or fallback


def _is_missing_campaign_error(exc: HTTPException) -> bool:
    if exc.status_code != status.HTTP_404_NOT_FOUND:
        return False
    detail = _http_detail_text(exc).lower()
    return "campaign" in detail or "autoresearch" in detail


def _scope_session_path(path: str, session_id: str | None) -> str:
    if not session_id:
        return path
    prefix = "/research-sessions/latest"
    if path == prefix:
        return f"/research-sessions/{session_id}"
    if path.startswith(prefix + "/"):
        return f"/research-sessions/{session_id}" + path[len(prefix):]
    return path


def _dispatch(
    request: DispatchRequest,
    settings: Settings,
    requester: Callable[..., tuple[str, dict[str, Any]]],
) -> DispatchResponse:
    parsed = _parse_command(request.message)
    if parsed is None:
        return DispatchResponse(
            matched=False,
            forward_to_openclaw=True,
            response_text="No deterministic command matched. Forward this turn to OpenClaw.",
        )

    command, argument = parsed
    submitted_by = request.submitted_by or settings.default_submitted_by
    pinned_session_id = request.session_id

    def scoped_requester(
        local_settings: Settings,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return requester(
            local_settings,
            _scope_session_path(path, pinned_session_id),
            method=method,
            body=body,
        )

    if command == "help":
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=_help_text(),
        )

    if command == "new-session":
        if len(argument) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!new-session needs a concrete goal after the command",
            )
        endpoint, payload = requester(
            settings,
            "/research-sessions",
            method="POST",
            body={
                "goal_statement": argument,
                "priorities": [],
                "submitted_by": submitted_by,
            },
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=(
                f"Created research session '{payload.get('title', 'untitled')}'. "
                "You can now add a PDF directly with !add-pdf <url>."
            ),
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command in {"start", "research", "search"}:
        if len(argument) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"!{command} needs a concrete topic after the command",
            )
        endpoint, payload = requester(
            settings,
            "/research-sessions/start-literature-search",
            method="POST",
            body={
                "goal_statement": argument,
                "priorities": [],
                "submitted_by": submitted_by,
            },
        )
        session = payload.get("session") or {}
        queue = payload.get("paper_intake_queue") or {}
        response_text = (
            f"Started literature search for session '{session.get('title', 'untitled')}'. "
            f"{_summarize_queue(queue)}"
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text.replace("Started literature search", "Started internet-backed literature search"),
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "more-papers":
        try:
            endpoint, payload = scoped_requester(
                settings,
                "/research-sessions/latest/skills/external-literature-search",
                method="POST",
            )
            source = "external literature search"
        except HTTPException:
            endpoint, payload = scoped_requester(
                settings,
                "/research-sessions/latest/skills/literature-harvest",
                method="POST",
            )
            source = "seed literature harvest"
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=f"Refreshed the paper queue from {source}. {_summarize_queue(payload)}",
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "next-paper":
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/paper-intake-queues/stage-next-intake",
            method="POST",
        )
        response_text = (
            f"Staged the next paper intake. Summary: {payload.get('normalized_summary', 'n/a')}"
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "add-paper":
        if not argument:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!add-paper needs a URL or paper title",
            )
        body = {
            "title": argument if not argument.startswith("http") else "Manual paper candidate",
            "official_page": argument if argument.startswith("http") else None,
            "pdf_url": argument if argument.startswith("http") and argument.endswith(".pdf") else None,
            "notes": ["Added from deterministic research command router."],
            "tags": ["manual"],
            "submitted_by": submitted_by,
        }
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/paper-intake-queue/manual-paper",
            method="POST",
            body=body,
        )
        candidates = payload.get("candidates") or []
        latest_title = candidates[-1]["title"] if candidates else argument
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=f"Added manual paper candidate '{latest_title}' to the current queue.",
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "add-dataset":
        if not argument or not argument.startswith("http"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!add-dataset needs a direct dataset URI or webpage URL",
            )
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/datasets",
            method="POST",
            body={
                "uri": argument,
                "submitted_by": submitted_by,
            },
        )
        dataset_name = payload.get("name") or argument
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=(
                f"Attached dataset '{dataset_name}' to the current workspace. "
                "Use !run when you want the backend to proceed with that dataset."
            ),
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "datasets":
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/datasets",
            method="GET",
        )
        datasets = payload if isinstance(payload, list) else []
        if not datasets:
            response_text = "No datasets are attached to the current workspace. Use !add-dataset <uri> first."
        else:
            lines = [
                f"{dataset.get('dataset_id', 'n/a')}: {dataset.get('name', dataset.get('uri', 'dataset'))}"
                for dataset in datasets[:5]
            ]
            response_text = "Attached datasets:\n" + "\n".join(lines)
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload={"datasets": datasets},
        )

    if command == "use-dataset":
        if not argument:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!use-dataset needs a dataset id",
            )
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/datasets/attach",
            method="POST",
            body={
                "dataset_id": argument,
            },
        )
        dataset_name = payload.get("name") or argument
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=f"Set active dataset to '{dataset_name}'.",
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "add-url":
        if not argument or not argument.startswith("http"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!add-url needs a direct webpage URL",
            )
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/source-documents/ingest",
            method="POST",
            body={
                "source_url": argument,
                "expected_title": None,
                "submitted_by": submitted_by,
            },
        )
        latest_title = _safe_source_label(payload.get("title"), argument, "web source")
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=(
                f"Attached webpage source '{latest_title}' to the current workspace. "
                "Use !run when you want the backend to proceed from the current session context."
            ),
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "add-pdf":
        if not argument or not argument.startswith("http"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!add-pdf needs a direct PDF URL",
            )
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/source-documents/ingest",
            method="POST",
            body={
                "source_url": argument,
                "expected_title": None,
                "submitted_by": submitted_by,
            },
        )
        latest_title = _safe_source_label(payload.get("title"), argument, "PDF source")
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=(
                f"Attached PDF source '{latest_title}' to the current workspace. "
                "Use !run when you want the backend to proceed from the current session context."
            ),
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command in {"status", "session"}:
        endpoint, payload = scoped_requester(settings, "/research-sessions/latest/context")
        session = payload.get("session") or {}
        queue = payload.get("paper_intake_queue") or {}
        active_dataset = payload.get("active_dataset") or {}
        response_text = (
            f"Active session '{session.get('title', 'untitled')}'. "
            f"Goal: {session.get('goal_statement', 'n/a')}. "
            f"Source queue: {queue.get('status', 'none')} with {len(queue.get('candidates') or [])} candidate(s)."
        )
        if active_dataset:
            response_text += f" Active dataset: {active_dataset.get('name', active_dataset.get('uri', 'dataset'))}."
        try:
            _context_endpoint, _context_payload, session_id = _get_latest_session_id(
                settings, scoped_requester, pinned_session_id
            )
            _summary_endpoint, summary_payload = scoped_requester(
                settings,
                f"/research-sessions/{session_id}/autoresearch-summary",
            )
            campaign = summary_payload.get("campaign") or {}
            iterations = summary_payload.get("iterations") or []
            response_text += (
                f" Campaign status: {campaign.get('status', 'active')} "
                f"with {len(iterations)} iteration(s)."
            )
        except HTTPException as exc:
            if not _is_missing_campaign_error(exc):
                raise
            response_text += " No autoresearch campaign yet."
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "interpret":
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/transitions/create-interpretation",
            method="POST",
        )
        response_text = (
            f"Created interpretation '{payload.get('interpretation_id', 'n/a')}'. "
            f"Preferred workflow: {payload.get('preferred_workflow_id', 'n/a')}."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "design":
        endpoint, payload = scoped_requester(
            settings,
            "/research-sessions/latest/skills/design",
            method="POST",
        )
        response_text = (
            f"Created design draft '{payload.get('design_id', 'n/a')}'. "
            f"Workflow: {payload.get('workflow_id', 'n/a')} ({payload.get('status', 'unknown')})."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "preflight":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        scoped_requester(
            settings,
            f"/research-sessions/{session_id}/skills/design",
            method="POST",
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/execution-preflight",
        )
        issues = payload.get("blocking_issues") or []
        warnings = payload.get("warnings") or []
        response_text = (
            f"Execution preflight for workflow '{payload.get('workflow_id', 'n/a')}' "
            f"has {len(issues)} blocking issue(s) and {len(warnings)} warning(s)."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "run":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        scoped_requester(
            settings,
            f"/research-sessions/{session_id}/skills/design",
            method="POST",
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/runs/from-design",
            method="POST",
        )
        response_text = (
            f"Created run '{payload.get('run_id', 'n/a')}' for workflow "
            f"'{payload.get('workflow_id', 'n/a')}'."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "start-autoresearch":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/start-autoresearch-campaign",
            method="POST",
        )
        response_text = (
            f"Started autoresearch campaign '{payload.get('campaign_id', 'n/a')}' "
            f"for objective '{payload.get('objective', 'n/a')}'."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "draft-methodologies":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/draft-methodologies",
            method="POST",
        )
        drafts = payload.get("methodology_drafts") or []
        response_text = f"Drafted {len(drafts)} methodology variant(s) for the active autoresearch campaign."
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "draft-notebook":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/draft-autoresearch-notebook",
            method="POST",
        )
        response_text = (
            f"Drafted analysis notebook at {payload.get('storage_uri', 'n/a')}."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "refine-notebook":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/refine-autoresearch-notebook",
            method="POST",
        )
        response_text = (
            f"Refined analysis notebook via {payload.get('refinement_source', 'unknown')} "
            f"at {payload.get('storage_uri', 'n/a')}."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "launch-iteration":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/launch-autoresearch-iteration",
            method="POST",
        )
        iteration = payload.get("iteration") or {}
        response_text = (
            f"Launched autoresearch iteration '{iteration.get('iteration_id', 'n/a')}' "
            f"with run '{iteration.get('run_id', 'n/a')}'."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "launch-batch":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/launch-autoresearch-batch",
            method="POST",
        )
        launches = payload.get("launches") or []
        response_text = f"Launched {len(launches)} autoresearch iteration(s) for the active campaign."
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "decide-latest":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/decide-autoresearch-latest",
            method="POST",
        )
        decision = payload.get("decision") or {}
        response_text = (
            f"Recorded autoresearch decision '{decision.get('decision_type', 'n/a')}' "
            f"for iteration '{decision.get('iteration_id', 'n/a')}'."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "decide-batch":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/decide-autoresearch-batch",
            method="POST",
        )
        decisions = payload.get("decisions") or []
        response_text = f"Recorded {len(decisions)} autoresearch decision(s) for ready completed iterations."
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "autoresearch":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        endpoint, payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/autoresearch-summary",
        )
        response_text = (
            f"Autoresearch summary: campaign '{payload.get('campaign', {}).get('campaign_id', 'n/a')}', "
            f"recommended model '{payload.get('recommended_model', 'n/a')}'."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command in {"compare", "model-comparison"}:
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        try:
            endpoint, payload = scoped_requester(
                settings,
                f"/research-sessions/{session_id}/autoresearch-model-comparison",
            )
        except HTTPException as exc:
            if _is_missing_campaign_error(exc):
                return DispatchResponse(
                    matched=True,
                    forward_to_openclaw=False,
                    command=command,
                    response_text="No autoresearch campaign yet. Use !next after !run to start one.",
                )
            raise
        comparison = payload.get("model_comparison") or []
        response_text = (
            f"Campaign comparison is ready with {len(comparison)} compared candidate(s). "
            f"Recommended model: {payload.get('recommended_model', 'n/a')}."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "next":
        _context_endpoint, _context_payload, session_id = _get_latest_session_id(
            settings, scoped_requester, pinned_session_id
        )
        campaign_exists = True
        try:
            scoped_requester(
                settings,
                f"/research-sessions/{session_id}/autoresearch-summary",
            )
        except HTTPException as exc:
            if _is_missing_campaign_error(exc):
                campaign_exists = False
            else:
                raise

        if not campaign_exists:
            drafted_endpoint, drafted_payload = scoped_requester(
                settings,
                f"/research-sessions/{session_id}/transitions/draft-methodologies",
                method="POST",
            )
            launch_endpoint, launch_payload = scoped_requester(
                settings,
                f"/research-sessions/{session_id}/transitions/launch-autoresearch-batch",
                method="POST",
            )
            drafts = drafted_payload.get("methodology_drafts") or []
            launches = launch_payload.get("launches") or []
            return DispatchResponse(
                matched=True,
                forward_to_openclaw=False,
                command=command,
                response_text=(
                    f"Started autoresearch, drafted {len(drafts)} variant(s), "
                    f"and launched {len(launches)} iteration(s)."
                ),
                workflow_api_endpoint=launch_endpoint,
                payload={
                    "drafted": drafted_payload,
                    "launch": launch_payload,
                    "draft_endpoint": drafted_endpoint,
                },
            )

        decide_endpoint, decide_payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/decide-autoresearch-batch",
            method="POST",
        )
        launch_endpoint, launch_payload = scoped_requester(
            settings,
            f"/research-sessions/{session_id}/transitions/launch-autoresearch-batch",
            method="POST",
        )
        decisions = decide_payload.get("decisions") or []
        launches = launch_payload.get("launches") or []
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=(
                f"Recorded {len(decisions)} completed decision(s) and launched "
                f"{len(launches)} next iteration(s)."
            ),
            workflow_api_endpoint=launch_endpoint,
            payload={
                "decide": decide_payload,
                "launch": launch_payload,
                "decide_endpoint": decide_endpoint,
            },
        )

    if command == "note":
        if not argument:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!note needs text after the command",
            )
        endpoint, payload = requester(
            settings,
            "/research-sessions/latest/memory",
            method="POST",
            body={"working_note": argument},
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text="Saved that note to the active research session.",
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "op":
        endpoint, payload = requester(settings, "/operations/latest")
        response_text = (
            f"Latest operation: {payload.get('operation_type', 'unknown')} "
            f"({payload.get('status', 'unknown')}). {payload.get('result_detail', '')}".strip()
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    return DispatchResponse(
        matched=False,
        forward_to_openclaw=True,
        response_text="No deterministic command matched. Forward this turn to OpenClaw.",
    )


def create_app(
    settings: Settings | None = None,
    requester: Callable[..., tuple[str, dict[str, Any]]] | None = None,
) -> FastAPI:
    active_settings = settings or Settings()
    active_requester = requester or _request_json

    app = FastAPI(title="Glasslab Research Command Router", version="0.1.0")

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            workflow_api_url=active_settings.workflow_api_url,
            timeout_seconds=active_settings.timeout_seconds,
        )

    @app.post("/dispatch", response_model=DispatchResponse)
    def dispatch(request: DispatchRequest) -> DispatchResponse:
        return _dispatch(request, active_settings, active_requester)

    return app
