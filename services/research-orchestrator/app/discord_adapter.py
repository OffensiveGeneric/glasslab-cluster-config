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
    components: list[dict[str, Any]] | None = None


def _action_title(action_type: str) -> str:
    return {
        'approve_protocol': 'Approve research protocol',
        'submit_experiment_matrix': 'Approve cluster experiment matrix',
        'accept_final_report': 'Accept final research report',
    }.get(action_type, action_type.replace('_', ' ').capitalize())


def _button_label(action_type: str, arguments: dict[str, Any]) -> str:
    if action_type == 'approve_protocol':
        return 'Approve protocol'
    if action_type == 'accept_final_report':
        return 'Accept report'
    if action_type == 'submit_experiment_matrix':
        variants = arguments.get('variants', [])
        seeds = arguments.get('seeds', [])
        job_count = (
            len(variants) * len(seeds)
            if isinstance(variants, list) and isinstance(seeds, list)
            else 0
        )
        return f'Approve {job_count} jobs' if job_count else 'Approve matrix'
    return 'Approve'


def _render_action_context(payload: dict[str, Any]) -> str:
    action_type = str(payload.get('type', 'action'))
    arguments = payload.get('arguments')
    if not isinstance(arguments, dict):
        arguments = {}
    ready = bool(payload.get('human_approval_ready', False))
    heading = (
        'Approval requested'
        if ready
        else 'Proposed action under methodology review'
    )
    lines = [
        f'**{heading}: {_action_title(action_type)}**',
        '',
        '**Research objective**',
        str(payload.get('objective', 'Not recorded.')),
    ]

    if action_type == 'approve_protocol':
        artifact = payload.get('artifact')
        if not isinstance(artifact, dict):
            artifact = {}
        lines.extend(
            [
                '',
                '**What you are reviewing**',
                (
                    f"Protocol v{payload.get('protocol_version', '?')} "
                    f"at `{artifact.get('uri', 'program.md')}` "
                    f"(SHA-256 `{str(artifact.get('sha256', 'unknown'))[:12]}...`)."
                ),
            ]
        )
    elif action_type == 'submit_experiment_matrix':
        variants = arguments.get('variants', [])
        seeds = arguments.get('seeds', [])
        resources = arguments.get('resources', {})
        if not isinstance(variants, list):
            variants = []
        if not isinstance(seeds, list):
            seeds = []
        if not isinstance(resources, dict):
            resources = {}
        variant_names = [
            str(item.get('name'))
            for item in variants
            if isinstance(item, dict) and item.get('name')
        ]
        job_count = len(variant_names) * len(seeds)
        lines.extend(
            [
                '',
                '**Experiment scope**',
                (
                    f"{job_count} jobs: {', '.join(variant_names) or 'unnamed variants'} "
                    f"across seeds {', '.join(map(str, seeds)) or 'not recorded'}."
                ),
                (
                    f"Per job: {resources.get('gpus', '?')} GPU, "
                    f"{resources.get('cpu', '?')} CPU, "
                    f"{resources.get('memory_gib', '?')} GiB RAM, "
                    f"up to {resources.get('wallclock_minutes', '?')} minutes."
                ),
                (
                    f"Concurrency: up to "
                    f"{arguments.get('maximum_parallel_jobs', '?')} jobs. "
                    f"Image: `{arguments.get('runner_image', 'not recorded')}`."
                ),
            ]
        )
    elif action_type == 'accept_final_report':
        artifact = payload.get('artifact')
        if not isinstance(artifact, dict):
            artifact = {}
        lines.extend(
            [
                '',
                '**Report being accepted**',
                (
                    f"`{artifact.get('uri', 'report.md')}` "
                    f"(SHA-256 `{str(artifact.get('sha256', 'unknown'))[:12]}...`)."
                ),
            ]
        )

    contract = payload.get('evaluation_contract')
    if isinstance(contract, dict):
        lines.extend(
            [
                '',
                '**Evaluation contract**',
                (
                    f"`{contract.get('contract_id', 'unknown')}` "
                    f"v{contract.get('version', '?')} "
                    f"(digest `{str(contract.get('digest', 'unknown'))[:12]}...`)."
                ),
            ]
        )
    lines.extend(
        [
            '',
            '**Why this gate exists**',
            str(payload.get('reason', 'Human review is required.')),
            '',
            '**Approval authorizes**',
            str(payload.get('effect', 'The stored action.')),
        ]
    )
    content = '\n'.join(lines)
    if len(content) <= 1900:
        return content
    return content[:1885].rstrip() + '\n...[details truncated]'


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
        if event_type in {
            'action.proposed',
            'action.human_approval_requested',
        }:
            components = None
            human_approval_ready = bool(
                payload.get(
                    'human_approval_ready',
                    payload.get('policy_classification')
                    != 'honeydew_and_human_approval',
                )
            )
            if (
                payload.get('approval_status') == 'pending'
                and human_approval_ready
            ):
                action_id = str(payload.get('action_id', ''))
                arguments = payload.get('arguments')
                if not isinstance(arguments, dict):
                    arguments = {}
                components = [
                    {
                        'type': 1,
                        'components': [
                            {
                                'type': 2,
                                'style': 3,
                                'label': _button_label(
                                    str(payload.get('type', '')),
                                    arguments,
                                ),
                                'custom_id': (
                                    f'glasslab:approve:{action_id}'
                                ),
                            },
                            {
                                'type': 2,
                                'style': 4,
                                'label': 'Reject',
                                'custom_id': (
                                    f'glasslab:reject:{action_id}'
                                ),
                            },
                        ],
                    }
                ]
            return DiscordMessage(
                identity,
                _render_action_context(payload),
                components=components,
            )
        if event_type in {'action.approved', 'action.rejected'}:
            return DiscordMessage(
                'Orchestrator',
                f"{event_type}: {payload.get('action_id')}",
            )
        if event_type == 'action.execution_failed':
            jobs_created = int(payload.get('jobs_created', 0))
            artifacts_created = int(payload.get('artifacts_created', 0))
            return DiscordMessage(
                'Orchestrator',
                '\n'.join(
                    [
                        '**Approved action could not be executed**',
                        '',
                        f"Action: `{payload.get('type', 'unknown')}`",
                        f"Error: {payload.get('error', 'Unknown error.')}",
                        (
                            'Recorded side effects: '
                            f'{jobs_created} job(s), '
                            f'{artifacts_created} artifact(s).'
                        ),
                        (
                            'Run state: '
                            f"`{payload.get('resulting_state', 'PAUSED')}`."
                        ),
                        f"Next step: {payload.get('next_step', 'Operator review.')}",
                    ]
                ),
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
        if (
            self.webhook_url
            and not message.is_status
            and not message.components
        ):
            self._publish_webhook(thread_id=thread_id, message=message)
            return status_message_id
        content = f'**{message.identity}:** {message.content}'[:2000]
        payload: dict[str, Any] = {'content': content}
        if message.components is not None:
            payload['components'] = message.components
        with self._client() as client:
            if message.is_status and status_message_id:
                response = client.patch(
                    f'/channels/{thread_id}/messages/{status_message_id}',
                    json=payload,
                )
            else:
                response = client.post(
                    f'/channels/{thread_id}/messages',
                    json=payload,
                )
            response.raise_for_status()
            if message.is_status and not status_message_id:
                return str(response.json()['id'])
        return status_message_id
