from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response
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
    gateway_base_url: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_BASE_URL",
        "http://glasslab-whatsapp-gateway.glasslab-v2.svc.cluster.local:8097",
    )
    meta_verify_token: str | None = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_META_VERIFY_TOKEN"
    )
    meta_access_token: str | None = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_META_ACCESS_TOKEN"
    )
    meta_phone_number_id: str | None = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_META_PHONE_NUMBER_ID"
    )
    meta_graph_api_base_url: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_META_GRAPH_API_BASE_URL",
        "https://graph.facebook.com/v23.0",
    )
    chat_backend_url: str | None = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_CHAT_BACKEND_URL"
    )
    chat_model: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_CHAT_MODEL",
        "qwen3:14b",
    )
    chat_timeout_seconds: int = int(
        os.environ.get("GLASSLAB_WHATSAPP_GATEWAY_CHAT_TIMEOUT_SECONDS", "120")
    )
    chat_history_messages: int = int(
        os.environ.get("GLASSLAB_WHATSAPP_GATEWAY_CHAT_HISTORY_MESSAGES", "12")
    )
    chat_system_prompt: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_CHAT_SYSTEM_PROMPT",
        (
            "You are the Glasslab assistant. Help researchers think through experiments, "
            "summarize results, and discuss next steps. Do not claim to execute actions "
            "unless a deterministic command is used. When appropriate, suggest commands "
            "like !start, !run, !next, !compare, !status, !new-session, or !add-pdf."
        ),
    )
    dm_policy: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_DM_POLICY",
        "open",
    )
    group_policy: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_GROUP_POLICY",
        "disabled",
    )
    owner: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_OWNER",
        "",
    )
    allow_from: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_ALLOW_FROM",
        "",
    )
    allow_groups: str = os.environ.get(
        "GLASSLAB_WHATSAPP_GATEWAY_ALLOW_GROUPS",
        "",
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
    session_id: str | None = None
    provider_message_id: str | None = None
    conversation_id: str | None = None
    is_group: bool = False
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

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


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
    meta_verify_enabled: bool
    meta_send_enabled: bool
    chat_enabled: bool
    dm_policy: str
    group_policy: str


class SessionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    role: str
    message: str
    forwarded_message: str | None = None
    provider_message_id: str | None = None
    workflow_session_id: str | None = None
    sender: str | None = None
    conversation_id: str | None = None
    is_group: bool = False
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
    conversation_id: str | None = None
    is_group: bool = False
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


class MetaWebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handled: bool
    provider: str
    processed_messages: int
    ignored_events: int
    results: list[dict[str, Any]] = Field(default_factory=list)


def _parse_csv_set(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _normalized_sender(sender: str) -> str:
    cleaned = " ".join(sender.split()).strip()
    if not cleaned:
        return cleaned
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[0]
    if ":" in cleaned:
        prefix, suffix = cleaned.split(":", 1)
        if prefix.lstrip("+").isdigit() and suffix.isdigit():
            cleaned = prefix
    if cleaned.isdigit():
        return f"+{cleaned}"
    if cleaned.startswith("+") and cleaned[1:].isdigit():
        return cleaned
    return cleaned


def _normalized_conversation_id(conversation_id: str | None) -> str:
    if not conversation_id:
        return ""
    cleaned = " ".join(conversation_id.split()).strip()
    if not cleaned:
        return cleaned
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[0]
    return cleaned


def _session_key(channel: str, sender: str, conversation_id: str | None = None) -> str:
    identity = conversation_id or sender
    safe_identity = "".join(ch if ch.isalnum() else "_" for ch in identity)
    return f"{channel}__{safe_identity}"


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
    sender: str | None = None,
    conversation_id: str | None = None,
    is_group: bool = False,
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
        sender=sender,
        conversation_id=conversation_id,
        is_group=is_group,
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


def _access_decision(
    settings: Settings,
    *,
    sender: str,
    conversation_id: str | None,
    is_group: bool,
) -> tuple[bool, str | None]:
    normalized_sender = _normalized_sender(sender)
    allowed_senders = _parse_csv_set(settings.allow_from)
    owner = _normalized_sender(settings.owner)
    if owner:
        allowed_senders.add(owner)
    allowed_groups = _parse_csv_set(settings.allow_groups)

    if is_group:
        policy = settings.group_policy.strip().lower()
        if policy == "disabled":
            return False, (
                "Group chat is not enabled in the Glasslab WhatsApp gateway yet. "
                "Use a direct message or a deterministic command path."
            )
        normalized_group = _normalized_conversation_id(conversation_id)
        if policy in {"open", "enabled"}:
            return True, None
        if policy == "allowlist":
            if (
                not conversation_id
                or (
                    conversation_id not in allowed_groups
                    and normalized_group not in allowed_groups
                )
            ):
                return False, "This group is not on the approved Glasslab allowlist."
        if policy in {"member-allowlist", "member_allowlist", "member"}:
            if normalized_sender not in allowed_senders:
                return False, "This sender is not on the approved Glasslab allowlist for group chat."
        return True, None

    policy = settings.dm_policy.strip().lower()
    if policy == "allowlist" and normalized_sender not in allowed_senders:
        return False, "This sender is not on the approved Glasslab allowlist."
    return True, None


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


def _meta_graph_endpoint(settings: Settings, path: str) -> str:
    return f"{settings.meta_graph_api_base_url.rstrip('/')}/{path.lstrip('/')}"


def _meta_headers(settings: Settings) -> dict[str, str]:
    token = (settings.meta_access_token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="meta access token is not configured",
        )
    return {"Authorization": f"Bearer {token}"}


def _meta_request_json(
    settings: Settings,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = _meta_graph_endpoint(settings, path)
    data = None
    headers = {
        "Accept": "application/json",
        **_meta_headers(settings),
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(endpoint, data=data, method=method, headers=headers)
    try:
        with urllib_request.urlopen(req, timeout=settings.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {"detail": exc.reason}
        raise HTTPException(status_code=exc.code, detail=detail)
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"meta graph api unreachable: {exc.reason}",
        )
    except (TimeoutError, socket.timeout):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="meta graph api timed out",
        )


def _fetch_meta_media_content(
    settings: Settings,
    media_id: str,
) -> tuple[bytes, str | None, str | None]:
    metadata = _meta_request_json(settings, media_id)
    media_url = str(metadata.get("url") or "").strip()
    if not media_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="meta media url missing",
        )
    req = urllib_request.Request(
        media_url,
        method="GET",
        headers=_meta_headers(settings),
    )
    try:
        with urllib_request.urlopen(req, timeout=settings.timeout_seconds) as response:
            content_type = response.headers.get("Content-Type")
            filename = None
            content_disposition = response.headers.get("Content-Disposition") or ""
            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=", 1)[1].strip().strip('"')
            return response.read(), content_type, filename
    except urllib_error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"meta media fetch failed: {exc.reason}")
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"meta media unreachable: {exc.reason}",
        )
    except (TimeoutError, socket.timeout):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="meta media fetch timed out",
        )


def _send_meta_text_reply(settings: Settings, *, recipient: str, text: str) -> dict[str, Any]:
    phone_number_id = str(settings.meta_phone_number_id or "").strip()
    if not phone_number_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="meta phone number id is not configured",
        )
    body = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    return _meta_request_json(settings, f"{phone_number_id}/messages", method="POST", body=body)


def _meta_attachment_record(settings: Settings, document: dict[str, Any]) -> AttachmentRecord | None:
    media_id = str(document.get("id") or "").strip()
    if not media_id:
        return None
    base = settings.gateway_base_url.rstrip("/")
    return AttachmentRecord(
        url=f"{base}/attachments/meta/{urllib_parse.quote(media_id, safe='')}",
        mime_type=str(document.get("mime_type") or "").strip() or None,
        filename=str(document.get("filename") or "").strip() or None,
    )


def _meta_webhook_requests(settings: Settings, payload: dict[str, Any]) -> tuple[list[ProviderWebhookRequest], int]:
    requests: list[ProviderWebhookRequest] = []
    ignored_events = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                sender = str(message.get("from") or "").strip()
                provider_message_id = str(message.get("id") or "").strip()
                if not sender or not provider_message_id:
                    ignored_events += 1
                    continue
                message_type = str(message.get("type") or "").strip().lower()
                text = ""
                attachments: list[AttachmentRecord] = []
                if message_type == "text":
                    text = str((message.get("text") or {}).get("body") or "").strip()
                elif message_type == "document":
                    document = message.get("document") or {}
                    attachment = _meta_attachment_record(settings, document)
                    if attachment is None:
                        ignored_events += 1
                        continue
                    attachments = [attachment]
                    text = str(document.get("caption") or "").strip()
                else:
                    ignored_events += 1
                    continue
                requests.append(
                    ProviderWebhookRequest(
                        provider="whatsapp",
                        provider_message_id=provider_message_id,
                        sender=sender,
                        text=text,
                        conversation_id=None,
                        is_group=False,
                        attachments=attachments,
                        channel=settings.default_channel,
                    )
                )
    return requests, ignored_events


def _chat_reply(
    settings: Settings,
    *,
    messages: list[SessionMessage],
    request: WhatsAppInboundRequest,
) -> str:
    backend_url = str(settings.chat_backend_url or "").strip()
    if not backend_url:
        return (
            "Free-form chat is not enabled in the Glasslab WhatsApp gateway yet. "
            "Use a deterministic command like !start, !run, !next, !compare, "
            "!status, !new-session, or !add-pdf."
        )

    prompt_messages: list[dict[str, str]] = [
        {"role": "system", "content": settings.chat_system_prompt.strip()}
    ]
    for prior in messages[-settings.chat_history_messages :]:
        if prior.role not in {"user", "assistant"}:
            continue
        content = prior.message
        if prior.role == "user" and prior.is_group and prior.sender:
            content = f"{prior.sender}: {content}"
        prompt_messages.append({"role": prior.role, "content": content})

    current_content = request.message
    if request.is_group:
        current_content = f"{request.sender}: {current_content}"
    prompt_messages.append({"role": "user", "content": current_content})

    body = json.dumps(
        {
            "model": settings.chat_model,
            "stream": False,
            "messages": prompt_messages,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        backend_url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=settings.chat_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = exc.reason
        raise HTTPException(
            status_code=exc.code,
            detail=f"chat backend request failed: {detail}",
        )
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"chat backend unreachable: {exc.reason}",
        )
    except (TimeoutError, socket.timeout):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="chat backend timed out",
        )

    message = payload.get("message")
    if not isinstance(message, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="chat backend response missing message object",
        )
    content = str(message.get("content") or "").strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="chat backend response missing message content",
        )
    return content


def _handle_inbound(
    active_settings: Settings,
    request: WhatsAppInboundRequest,
) -> InboundForwardResponse:
    channel = request.channel or active_settings.default_channel
    session_key = _session_key(channel, request.sender, request.conversation_id)
    forwarded_message = _augment_message_for_attachments(request)
    if not forwarded_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message is empty and no supported attachment action could be inferred",
        )

    prior_messages = _load_messages(active_settings, session_key)
    pinned_session_id = request.session_id or _latest_workflow_session_id(prior_messages)
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

    access_allowed, denial_message = _access_decision(
        active_settings,
        sender=request.sender,
        conversation_id=request.conversation_id,
        is_group=request.is_group,
    )
    if not access_allowed:
        _append_message(
            active_settings,
            session_key=session_key,
            role="user",
            message=request.message,
            forwarded_message=forwarded_message,
            provider_message_id=provider_message_id,
            workflow_session_id=pinned_session_id,
            sender=request.sender,
            conversation_id=request.conversation_id,
            is_group=request.is_group,
            attachments=request.attachments,
        )
        _append_message(
            active_settings,
            session_key=session_key,
            role="assistant",
            message=denial_message or "Access denied.",
            sender=None,
            conversation_id=request.conversation_id,
            is_group=request.is_group,
            attachments=[],
            route="gateway-policy",
            handled=False,
        )
        return InboundForwardResponse(
            handled=False,
            route="gateway-policy",
            response_text=denial_message or "Access denied.",
            forwarded_message=forwarded_message,
            session_key=session_key,
            router_payload={"policy_denied": True},
        )

    _append_message(
        active_settings,
        session_key=session_key,
        role="user",
        message=request.message,
        forwarded_message=forwarded_message,
        provider_message_id=provider_message_id,
        workflow_session_id=pinned_session_id,
        sender=request.sender,
        conversation_id=request.conversation_id,
        is_group=request.is_group,
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
        if str(active_settings.chat_backend_url or "").strip():
            response_text = _chat_reply(
                active_settings,
                messages=_load_messages(active_settings, session_key),
                request=request,
            )
            route = "gateway-chat"
            handled = True
        else:
            response_text = (
                "Free-form chat is not enabled in the Glasslab WhatsApp gateway yet. "
                "Use a deterministic command like !start, !run, !next, !compare, "
                "!status, !new-session, or !add-pdf."
            )
            route = str(ingress_payload.get("route") or "openclaw-fallback")
            handled = False
    else:
        route = str(ingress_payload.get("route") or "unknown")
        handled = bool(ingress_payload.get("handled"))
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
        sender=None,
        conversation_id=request.conversation_id,
        is_group=request.is_group,
        attachments=[],
        route=route,
        handled=handled,
    )
    return InboundForwardResponse(
        handled=handled,
        route=route,
        response_text=response_text,
        forwarded_message=forwarded_message,
        session_key=session_key,
        router_payload=(
            ingress_payload.get("router_payload")
            if route != "gateway-chat"
            else {"chat_backend": True}
        ),
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
            meta_verify_enabled=bool((active_settings.meta_verify_token or "").strip()),
            meta_send_enabled=bool(
                (active_settings.meta_access_token or "").strip()
                and (active_settings.meta_phone_number_id or "").strip()
            ),
            chat_enabled=bool((active_settings.chat_backend_url or "").strip()),
            dm_policy=active_settings.dm_policy,
            group_policy=active_settings.group_policy,
        )

    @app.post("/webhooks/whatsapp/inbound", response_model=InboundForwardResponse)
    def whatsapp_inbound(request: WhatsAppInboundRequest) -> InboundForwardResponse:
        return _handle_inbound(active_settings, request)

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

    @app.get("/webhooks/meta/whatsapp")
    def meta_whatsapp_verify(
        hub_mode: str | None = Query(default=None, alias="hub.mode"),
        hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
        hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    ) -> PlainTextResponse:
        expected = str(active_settings.meta_verify_token or "").strip()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="meta verify token is not configured",
            )
        if hub_mode != "subscribe" or hub_verify_token != expected:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="meta webhook verification failed",
            )
        return PlainTextResponse(hub_challenge or "")

    @app.post("/webhooks/meta/whatsapp", response_model=MetaWebhookResponse)
    def meta_whatsapp_webhook(payload: dict[str, Any]) -> MetaWebhookResponse:
        requests, ignored_events = _meta_webhook_requests(active_settings, payload)
        results: list[dict[str, Any]] = []
        for request in requests:
            response = _handle_inbound(
                active_settings,
                WhatsAppInboundRequest(
                    sender=request.sender,
                    channel=request.channel,
                    message=request.text,
                    provider_message_id=request.provider_message_id,
                    attachments=request.attachments,
                ),
            )
            result: dict[str, Any] = {
                "provider_message_id": request.provider_message_id,
                "sender": request.sender,
                "forwarded_message": response.forwarded_message,
                "route": response.route,
                "handled": response.handled,
                "session_key": response.session_key,
            }
            if (
                bool((active_settings.meta_access_token or "").strip())
                and bool((active_settings.meta_phone_number_id or "").strip())
                and response.response_text.strip()
            ):
                outbound = _send_meta_text_reply(
                    active_settings,
                    recipient=request.sender,
                    text=response.response_text,
                )
                result["reply_sent"] = True
                result["reply_payload"] = outbound
            else:
                result["reply_sent"] = False
            results.append(result)
        return MetaWebhookResponse(
            handled=True,
            provider="meta-whatsapp",
            processed_messages=len(results),
            ignored_events=ignored_events,
            results=results,
        )

    @app.get("/attachments/meta/{media_id}")
    def meta_attachment_proxy(media_id: str) -> Response:
        payload, content_type, _ = _fetch_meta_media_content(active_settings, media_id)
        return Response(
            content=payload,
            media_type=content_type or "application/octet-stream",
        )

    @app.get("/sessions/{channel}/{sender}", response_model=SessionTranscriptResponse)
    def session_transcript(channel: str, sender: str) -> SessionTranscriptResponse:
        session_key = _session_key(channel, sender)
        return SessionTranscriptResponse(
            session_key=session_key,
            messages=_load_messages(active_settings, session_key),
        )

    return app
