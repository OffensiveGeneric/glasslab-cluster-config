from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class Settings:
    workflow_api_url: str = os.environ.get(
        "GLASSLAB_RESEARCH_COMMAND_ROUTER_WORKFLOW_API_URL",
        "http://glasslab-workflow-api.glasslab-v2.svc.cluster.local:8080",
    )
    timeout_seconds: int = int(
        os.environ.get("GLASSLAB_RESEARCH_COMMAND_ROUTER_TIMEOUT_SECONDS", "30")
    )
    default_submitted_by: str = os.environ.get(
        "GLASSLAB_RESEARCH_COMMAND_ROUTER_SUBMITTED_BY",
        "research-command-router",
    )


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    submitted_by: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("message must not be empty")
        return cleaned


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
        ("!research", "research"),
        ("research:", "research"),
        ("!more-papers", "more-papers"),
        ("papers:", "more-papers"),
        ("!next-paper", "next-paper"),
        ("next-paper:", "next-paper"),
        ("!add-paper", "add-paper"),
        ("add-paper:", "add-paper"),
        ("!session", "session"),
        ("session:", "session"),
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
            "Supported research commands:",
            "!research <topic>",
            "!more-papers",
            "!next-paper",
            "!add-paper <url|title>",
            "!session",
            "!note <text>",
            "!op",
            "!help",
        ]
    )


def _summarize_queue(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    coverage = payload.get("coverage_summary") or {}
    mode = coverage.get("mode") or coverage.get("provider") or "queue"
    return (
        f"Queue ready with {len(candidates)} candidate paper(s). "
        f"Coverage mode: {mode}."
    )


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

    if command == "help":
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=_help_text(),
        )

    if command == "research":
        if len(argument) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="!research needs a concrete topic after the command",
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
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
        )

    if command == "more-papers":
        try:
            endpoint, payload = requester(
                settings,
                "/research-sessions/latest/skills/external-literature-search",
                method="POST",
            )
            source = "external literature search"
        except HTTPException:
            endpoint, payload = requester(
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
        endpoint, payload = requester(
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
        endpoint, payload = requester(
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

    if command == "session":
        endpoint, payload = requester(settings, "/research-sessions/latest/context")
        session = payload.get("session") or {}
        queue = payload.get("paper_intake_queue") or {}
        response_text = (
            f"Current session: '{session.get('title', 'untitled')}'. "
            f"Goal: {session.get('goal_statement', 'n/a')}. "
            f"Queue status: {queue.get('status', 'none')} with {len(queue.get('candidates') or [])} candidate(s)."
        )
        return DispatchResponse(
            matched=True,
            forward_to_openclaw=False,
            command=command,
            response_text=response_text,
            workflow_api_endpoint=endpoint,
            payload=payload,
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
