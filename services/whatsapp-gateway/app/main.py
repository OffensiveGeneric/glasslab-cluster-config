from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Settings:
    research_ingress_url: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_RESEARCH_INGRESS_URL",
        "http://glasslab-research-ingress.glasslab-v2.svc.cluster.local:8096",
    )
    timeout_seconds: int = int(
        os.environ.get("GLASSLAB_WHATSAPP_GATEWAY_TIMEOUT_SECONDS", "120")
    )
    state_dir: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_STATE_DIR",
        "/tmp/glasslab-whatsapp-gateway",
    )
    default_channel: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_DEFAULT_CHANNEL",
        "whatsapp",
    )


class AttachmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    mime_type: str | None = None
    filename: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("url must not be empty")
        return cleaned


class WhatsAppInboundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender: str = Field(min_length=1)
    channel: str | None = None
    message: str = ""
    provider_message_id: str | None = None
    attachments: list[AttachmentRecord] = Field(default_factory=list)

    @field_validator("sender")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("sender must not be empty")
        return cleaned

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        return " ".join(value.split()).strip()


class InboundForwardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handled: bool
    route: str
    response_text: str
    forwarded_message: str
    session_key: str
    router_payload: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    research_ingress_url: str
    state_dir: str
    timeout_seconds: int


class SessionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    role: str
    message: str
    forwarded_message: str | None = None
    provider_message_id: str | None = None
    workflow_session_id: str | None = None
    attachments: list[AttachmentRecord] = Field(default_factory=list)
    route: str | None = None
    handled: bool | None = None


class SessionTranscriptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_key: str
    messages: list[SessionMessage]


class ProviderWebhookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    provider_message_id: str = Field(min_length=1)
    sender: str = Field(min_length=1)
    text: str = ""
    attachments: list[AttachmentRecord] = Field(default_factory=list)
    channel: str | None = None

    @field_validator("provider", "provider_message_id", "sender")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split()).strip()


def _session_key(channel: str, sender: str) -> str:
    safe_sender = "".join(ch if ch.isalnum() else "_" for ch in sender)
    return f"{channel}__{safe_sender}"


def _session_path(settings: Settings, session_key: str) -> Path:
    state_dir = Path(settings.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / f"{session_key}.jsonl"


def _append_message(
    settings: Settings,
    *,
    session_key: str,
    role: str,
    message: str,
    forwarded_message: str | None = None,
    provider_message_id: str | None = None,
    workflow_session_id: str | None = None,
    attachments: list[AttachmentRecord],
    route: str | None = None,
    handled: bool | None = None,
) -> None:
    payload = SessionMessage(
        timestamp=_utc_now_iso(),
        role=role,
        message=message,
        forwarded_message=forwarded_message,
        provider_message_id=provider_message_id,
        workflow_session_id=workflow_session_id,
        attachments=attachments,
        route=route,
        handled=handled,
    )
    path = _session_path(settings, session_key)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload.model_dump_json())
        handle.write("\n")


def _load_messages(settings: Settings, session_key: str) -> list[SessionMessage]:
    path = _session_path(settings, session_key)
    if not path.exists():
        return []
    messages: list[SessionMessage] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            messages.append(SessionMessage.model_validate_json(line))
    return messages


def _is_pdf_attachment(attachment: AttachmentRecord) -> bool:
    mime = (attachment.mime_type or "").lower()
    filename = (attachment.filename or "").lower()
    url = attachment.url.lower()
    return (
        mime == "application/pdf"
        or filename.endswith(".pdf")
        or url.endswith(".pdf")
    )


def _latest_pdf_url(attachments: list[AttachmentRecord]) -> str | None:
    for attachment in reversed(attachments):
        if _is_pdf_attachment(attachment):
            return attachment.url
    return None


def _augment_message_for_attachments(request: WhatsAppInboundRequest) -> str:
    message = request.message.strip()
    if not request.attachments:
        return message
    pdf_url = _latest_pdf_url(request.attachments)
    if pdf_url is None:
        return message
    if not message:
        return f"!add-pdf {pdf_url}"
    lowered = message.lower()
    if lowered == "!add-pdf":
        return f"!add-pdf {pdf_url}"
    return message


def _attachment_signature(attachments: list[AttachmentRecord]) -> list[tuple[str, str | None, str | None]]:
    return [
        (attachment.url, attachment.mime_type, attachment.filename)
        for attachment in attachments
    ]


def _find_duplicate_response(
    messages: list[SessionMessage],
    *,
    raw_message: str,
    forwarded_message: str,
    attachments: list[AttachmentRecord],
) -> SessionMessage | None:
    if len(messages) < 2:
        return None
    last_assistant = messages[-1]
    last_user = messages[-2]
    if last_user.role != "user" or last_assistant.role != "assistant":
        return None
    if (last_user.forwarded_message or "") != forwarded_message:
        return None
    if last_user.message != raw_message:
        return None
    if _attachment_signature(last_user.attachments) != _attachment_signature(attachments):
        return None
    return last_assistant


def _find_response_for_provider_message_id(
    messages: list[SessionMessage],
    provider_message_id: str,
) -> SessionMessage | None:
    if not provider_message_id:
        return None
    for index in range(len(messages) - 1):
        current = messages[index]
        nxt = messages[index + 1]
        if (
            current.role == "user"
            and current.provider_message_id == provider_message_id
            and nxt.role == "assistant"
        ):
            return nxt
    return None


def _latest_workflow_session_id(messages: list[SessionMessage]) -> str | None:
    for message in reversed(messages):
        session_id = (message.workflow_session_id or "").strip()
        if session_id:
            return session_id
    return None


def _extract_workflow_session_id(router_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(router_payload, dict):
        return None
    payload = router_payload.get("payload")
    if isinstance(payload, dict):
        session = payload.get("session")
        if isinstance(session, dict):
            session_id = str(session.get("session_id") or "").strip()
            if session_id:
                return session_id
        session_id = str(payload.get("session_id") or "").strip()
        if session_id:
            return session_id
    return None


def _request_research_ingress(
    settings: Settings,
    *,
    message: str,
    sender: str,
    channel: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    endpoint = f"{settings.research_ingress_url.rstrip('/')}/inbound"
    payload: dict[str, Any] = {
        "message": message,
        "sender": sender,
        "channel": channel,
    }
    if session_id:
        payload["session_id"] = session_id
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=settings.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {"detail": exc.reason}
        raise HTTPException(status_code=exc.code, detail=detail.get("detail", detail))
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"research-ingress unreachable: {exc.reason}",
        )
    except (TimeoutError, socket.timeout):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="research-ingress timed out",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title="Glasslab WhatsApp Gateway", version="0.1.0")

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            research_ingress_url=active_settings.research_ingress_url,
            state_dir=active_settings.state_dir,
            timeout_seconds=active_settings.timeout_seconds,
        )

    @app.post("/webhooks/whatsapp/inbound", response_model=InboundForwardResponse)
    def whatsapp_inbound(request: WhatsAppInboundRequest) -> InboundForwardResponse:
        channel = request.channel or active_settings.default_channel
        session_key = _session_key(channel, request.sender)
        forwarded_message = _augment_message_for_attachments(request)
        if not forwarded_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="message is empty and no supported attachment action could be inferred",
            )

        prior_messages = _load_messages(active_settings, session_key)
        pinned_session_id = _latest_workflow_session_id(prior_messages)
        provider_message_id = (request.provider_message_id or "").strip() or None
        if provider_message_id is not None:
            provider_dedupe = _find_response_for_provider_message_id(
                prior_messages,
                provider_message_id,
            )
            if provider_dedupe is not None:
                return InboundForwardResponse(
                    handled=bool(provider_dedupe.handled),
                    route=str(provider_dedupe.route or "provider-duplicate-suppressed"),
                    response_text=provider_dedupe.message,
                    forwarded_message=forwarded_message,
                    session_key=session_key,
                    router_payload={
                        "duplicate_suppressed": True,
                        "duplicate_scope": "provider_message_id",
                        "provider_message_id": provider_message_id,
                    },
                )
        duplicate_response = _find_duplicate_response(
            prior_messages,
            raw_message=request.message,
            forwarded_message=forwarded_message,
            attachments=request.attachments,
        )
        if duplicate_response is not None:
            return InboundForwardResponse(
                handled=bool(duplicate_response.handled),
                route=str(duplicate_response.route or "duplicate-suppressed"),
                response_text=duplicate_response.message,
                forwarded_message=forwarded_message,
                session_key=session_key,
                router_payload={"duplicate_suppressed": True},
            )

        _append_message(
            active_settings,
            session_key=session_key,
            role="user",
            message=request.message,
            forwarded_message=forwarded_message,
            provider_message_id=provider_message_id,
            workflow_session_id=pinned_session_id,
            attachments=request.attachments,
        )
        ingress_payload = _request_research_ingress(
            active_settings,
            message=forwarded_message,
            sender=request.sender,
            channel=channel,
            session_id=(
                None
                if forwarded_message.lower().startswith(("!new-session", "!start", "!research"))
                else pinned_session_id
            ),
        )
        response_text = str(ingress_payload.get("response_text") or "").strip()
        if (
            not ingress_payload.get("handled")
            and ingress_payload.get("forward_to_openclaw")
        ):
            response_text = (
                "Free-form chat is not enabled in the Glasslab WhatsApp gateway yet. "
                "Use a deterministic command like !start, !run, !next, !compare, "
                "!status, !new-session, or !add-pdf."
            )
        if not response_text:
            response_text = "No response text was returned by research-ingress."
        _append_message(
            active_settings,
            session_key=session_key,
            role="assistant",
            message=response_text,
            forwarded_message=None,
            provider_message_id=None,
            workflow_session_id=_extract_workflow_session_id(
                ingress_payload.get("router_payload")
            ) or pinned_session_id,
            attachments=[],
            route=str(ingress_payload.get("route") or ""),
            handled=bool(ingress_payload.get("handled")),
        )
        return InboundForwardResponse(
            handled=bool(ingress_payload.get("handled")),
            route=str(ingress_payload.get("route") or "unknown"),
            response_text=response_text,
            forwarded_message=forwarded_message,
            session_key=session_key,
            router_payload=ingress_payload.get("router_payload"),
        )

    @app.post("/webhooks/whatsapp/provider", response_model=InboundForwardResponse)
    def whatsapp_provider_webhook(
        request: ProviderWebhookRequest,
    ) -> InboundForwardResponse:
        if request.provider.lower() != "whatsapp":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="unsupported provider",
            )
        return whatsapp_inbound(
            WhatsAppInboundRequest(
                sender=request.sender,
                channel=request.channel or active_settings.default_channel,
                message=request.text,
                provider_message_id=request.provider_message_id,
                attachments=request.attachments,
            )
        )

    @app.get("/sessions/{channel}/{sender}", response_model=SessionTranscriptResponse)
    def session_transcript(channel: str, sender: str) -> SessionTranscriptResponse:
        session_key = _session_key(channel, sender)
        return SessionTranscriptResponse(
            session_key=session_key,
            messages=_load_messages(active_settings, session_key),
        )

    return app
