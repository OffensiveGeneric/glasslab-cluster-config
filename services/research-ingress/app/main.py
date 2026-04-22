from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class Settings:
    command_router_url: str = os.environ.get(
        "GLASSLAB_RESEARCH_INGRESS_COMMAND_ROUTER_URL",
        "http://glasslab-research-command-router.glasslab-v2.svc.cluster.local:8095",
    )
    timeout_seconds: int = int(
        os.environ.get("GLASSLAB_RESEARCH_INGRESS_TIMEOUT_SECONDS", "120")
    )
    default_channel: str = os.environ.get(
        "GLASSLAB_RESEARCH_INGRESS_DEFAULT_CHANNEL",
        "whatsapp",
    )


class InboundMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    sender: str = Field(min_length=1)
    channel: str | None = None
    session_id: str | None = None

    @field_validator("message", "sender")
    @classmethod
    def validate_text_field(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned


class InboundMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handled: bool
    route: str
    response_text: str
    router_payload: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    command_router_url: str
    timeout_seconds: int


def _request_router(
    settings: Settings,
    message: str,
    submitted_by: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    endpoint = f"{settings.command_router_url.rstrip('/')}/dispatch"
    payload = {
        "message": message,
        "submitted_by": submitted_by,
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
            detail=f"research-command-router unreachable: {exc.reason}",
        )
    except (TimeoutError, socket.timeout):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="research-command-router timed out",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title="Glasslab Research Ingress", version="0.1.0")

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            command_router_url=active_settings.command_router_url,
            timeout_seconds=active_settings.timeout_seconds,
        )

    @app.post("/inbound", response_model=InboundMessageResponse)
    def inbound(request: InboundMessageRequest) -> InboundMessageResponse:
        channel = request.channel or active_settings.default_channel
        router_payload = _request_router(
            active_settings,
            request.message,
            submitted_by=f"{channel}:{request.sender}",
            session_id=request.session_id,
        )
        if router_payload.get("matched"):
            return InboundMessageResponse(
                handled=True,
                route="deterministic-router",
                response_text=router_payload.get("response_text", ""),
                router_payload=router_payload,
            )

        return InboundMessageResponse(
            handled=True,
            route="unsupported-turn",
            response_text=router_payload.get("response_text", ""),
            router_payload=router_payload,
        )

    return app
