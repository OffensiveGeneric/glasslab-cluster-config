from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .schemas import EventRecord


@dataclass(frozen=True)
class DiscordMessage:
    identity: str
    content: str
    is_status: bool = False


class DiscordRenderer:
    IDENTITIES = {
        'honeydew': 'Honeydew',
        'beaker': 'Beaker',
        'orchestrator': 'Orchestrator',
        'cluster': 'Orchestrator',
    }

    def render(self, event: EventRecord) -> DiscordMessage | None:
        identity = self.IDENTITIES.get(event.source, 'Orchestrator')
        event_type = event.event_type
        payload = event.payload
        if event_type == 'run.created':
            return DiscordMessage(
                'Orchestrator',
                f"Research run created: {payload.get('objective', '')}",
            )
        if event_type == 'run.state_changed':
            return DiscordMessage(
                'Orchestrator',
                f"State: {payload.get('from')} -> {payload.get('to')}",
                is_status=True,
            )
        if event_type == 'agent.turn_completed':
            content = str(payload.get('summary', 'Agent turn completed.'))
            handoff = str(payload.get('message_to_other_agent', '')).strip()
            if handoff:
                recipient = 'Beaker' if identity == 'Honeydew' else 'Honeydew'
                content = f'{content}\n\n**To {recipient}:** {handoff}'
            return DiscordMessage(
                identity,
                content,
            )
        if event_type == 'action.proposed':
            return DiscordMessage(
                identity,
                (
                    f"Action proposed: {payload.get('type')} "
                    f"({payload.get('policy_classification')})"
                ),
            )
        if event_type in {'action.approved', 'action.rejected'}:
            return DiscordMessage(
                'Orchestrator',
                f"{event_type}: {payload.get('action_id')}",
            )
        if event_type in {'job.submitted', 'job.completed', 'job.failed'}:
            return DiscordMessage(
                'Orchestrator',
                f"{event_type}: {payload.get('job_id')}",
            )
        if event_type == 'report.created':
            return DiscordMessage(
                'Honeydew',
                f"Report ready: {payload.get('uri')}",
            )
        if event_type in {
            'run.paused',
            'run.cancelled',
            'run.completed',
            'run.failed',
        }:
            return DiscordMessage(
                'Orchestrator',
                event_type.replace('.', ' ').capitalize(),
                is_status=True,
            )
        return None


class DiscordAdapter(ABC):
    @abstractmethod
    def create_thread(self, *, run_id: str, objective: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def publish(
        self,
        *,
        thread_id: str | None,
        status_message_id: str | None,
        event: EventRecord,
    ) -> str | None:
        raise NotImplementedError


class DisabledDiscordAdapter(DiscordAdapter):
    def create_thread(self, *, run_id: str, objective: str) -> str | None:
        return None

    def publish(
        self,
        *,
        thread_id: str | None,
        status_message_id: str | None,
        event: EventRecord,
    ) -> str | None:
        return status_message_id


class DiscordHttpAdapter(DiscordAdapter):
    """Minimal REST projection. It is not workflow state or agent memory."""

    def __init__(
        self,
        *,
        bot_token: str,
        channel_id: str,
        webhook_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.webhook_url = webhook_url
        self.transport = transport
        self.renderer = DiscordRenderer()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url='https://discord.com/api/v10',
            headers={'Authorization': f'Bot {self.bot_token}'},
            timeout=15,
            transport=self.transport,
        )

    def create_thread(self, *, run_id: str, objective: str) -> str | None:
        name = f'research-{run_id[:8]}'
        with self._client() as client:
            response = client.post(
                f'/channels/{self.channel_id}/threads',
                json={
                    'name': name,
                    'type': 11,
                    'auto_archive_duration': 1440,
                },
                headers={
                    'X-Audit-Log-Reason': quote(
                        f'Glasslab research run: {objective[:400]}'
                    ),
                },
            )
            response.raise_for_status()
            return str(response.json()['id'])

    def _publish_webhook(
        self,
        *,
        thread_id: str,
        message: DiscordMessage,
    ) -> None:
        if self.webhook_url is None:
            raise RuntimeError('Discord webhook URL is not configured')
        with httpx.Client(timeout=15, transport=self.transport) as client:
            response = client.post(
                self.webhook_url,
                params={'wait': 'true', 'thread_id': thread_id},
                json={
                    'username': message.identity,
                    'content': message.content[:2000],
                    'allowed_mentions': {'parse': []},
                },
            )
        if response.is_error:
            raise RuntimeError(
                f'Discord webhook returned HTTP {response.status_code}'
            )

    def publish(
        self,
        *,
        thread_id: str | None,
        status_message_id: str | None,
        event: EventRecord,
    ) -> str | None:
        if thread_id is None:
            return status_message_id
        message = self.renderer.render(event)
        if message is None:
            return status_message_id
        if self.webhook_url and not message.is_status:
            self._publish_webhook(thread_id=thread_id, message=message)
            return status_message_id
        content = f'**{message.identity}:** {message.content}'[:2000]
        with self._client() as client:
            if message.is_status and status_message_id:
                response = client.patch(
                    f'/channels/{thread_id}/messages/{status_message_id}',
                    json={'content': content},
                )
            else:
                response = client.post(
                    f'/channels/{thread_id}/messages',
                    json={'content': content},
                )
            response.raise_for_status()
            if message.is_status and not status_message_id:
                return str(response.json()['id'])
        return status_message_id
