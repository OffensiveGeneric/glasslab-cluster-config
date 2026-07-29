from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from .schemas import ApprovalStatus

if TYPE_CHECKING:
    from .engine import ResearchOrchestrator


CONTROL_PREFIX = 'glasslab'


@dataclass(frozen=True)
class DiscordControlActor:
    user_id: str
    display_name: str
    guild_id: str | None
    role_ids: frozenset[str]

    @property
    def reviewer(self) -> str:
        return f'discord:{self.user_id}:{self.display_name}'


class DiscordControlPolicy:
    def __init__(
        self,
        *,
        guild_id: str,
        admin_role_id: str | None,
        admin_user_ids: list[str],
    ) -> None:
        self.guild_id = guild_id
        self.admin_role_id = admin_role_id
        self.admin_user_ids = frozenset(admin_user_ids)

    def is_authorized(self, actor: DiscordControlActor) -> bool:
        if actor.guild_id != self.guild_id:
            return False
        if actor.user_id in self.admin_user_ids:
            return True
        return bool(
            self.admin_role_id
            and self.admin_role_id in actor.role_ids
        )


def execute_discord_action(
    engine: ResearchOrchestrator,
    *,
    operation: str,
    action_id: str,
    actor: DiscordControlActor,
) -> None:
    if operation == 'approve':
        engine.approve_action(
            action_id,
            reviewer=actor.reviewer,
            reason='Approved through Discord controls.',
        )
    elif operation == 'reject':
        engine.reject_action(
            action_id,
            reviewer=actor.reviewer,
            reason='Rejected through Discord controls.',
        )
    else:
        raise ValueError(f'unsupported Discord operation: {operation}')


class DiscordControlGateway:
    """Outbound Gateway listener for bounded approval-button interactions."""

    def __init__(
        self,
        *,
        engine: ResearchOrchestrator,
        bot_token: str,
        guild_id: str,
        admin_role_id: str | None,
        admin_user_ids: list[str],
    ) -> None:
        self.engine = engine
        self.bot_token = bot_token
        self.policy = DiscordControlPolicy(
            guild_id=guild_id,
            admin_role_id=admin_role_id,
            admin_user_ids=admin_user_ids,
        )
        intents = discord.Intents.none()
        intents.guilds = True
        self.client = discord.Client(intents=intents)
        self.client.add_listener(self._on_interaction, 'on_interaction')
        self._tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        await self.client.start(self.bot_token, reconnect=True)

    async def close(self) -> None:
        await self.client.close()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @staticmethod
    def _actor(interaction: discord.Interaction) -> DiscordControlActor:
        role_ids: set[str] = set()
        if isinstance(interaction.user, discord.Member):
            role_ids = {str(role.id) for role in interaction.user.roles}
        return DiscordControlActor(
            user_id=str(interaction.user.id),
            display_name=interaction.user.display_name,
            guild_id=(
                str(interaction.guild_id)
                if interaction.guild_id is not None
                else None
            ),
            role_ids=frozenset(role_ids),
        )

    async def _respond(
        self,
        interaction: discord.Interaction,
        content: str,
    ) -> None:
        await interaction.response.send_message(
            content,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _on_interaction(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.type != discord.InteractionType.component:
            return
        data = interaction.data
        if not isinstance(data, dict):
            return
        custom_id = str(data.get('custom_id', ''))
        parts = custom_id.split(':', 2)
        if len(parts) != 3 or parts[0] != CONTROL_PREFIX:
            return
        operation, action_id = parts[1:]
        if operation not in {'approve', 'reject'}:
            return

        actor = self._actor(interaction)
        if not self.policy.is_authorized(actor):
            await self._respond(
                interaction,
                'You are not authorized to control Glasslab research runs.',
            )
            return
        try:
            action = self.engine.store.get_action(action_id)
            run = self.engine.store.get_run(action.run_id)
        except Exception:
            await self._respond(interaction, 'This action no longer exists.')
            return
        if (
            run.discord_thread_id is None
            or str(interaction.channel_id) != run.discord_thread_id
        ):
            await self._respond(
                interaction,
                'This control is not attached to this research thread.',
            )
            return
        if action.approval_status != ApprovalStatus.PENDING:
            await self._respond(
                interaction,
                f'This action is already {action.approval_status.value}.',
            )
            return

        await self._respond(
            interaction,
            (
                f'{operation.capitalize()} request received. '
                'The authoritative result will be posted in this thread.'
            ),
        )
        task = asyncio.create_task(
            self._execute(
                interaction=interaction,
                operation=operation,
                action_id=action_id,
                actor=actor,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _execute(
        self,
        *,
        interaction: discord.Interaction,
        operation: str,
        action_id: str,
        actor: DiscordControlActor,
    ) -> None:
        try:
            await asyncio.to_thread(
                execute_discord_action,
                self.engine,
                operation=operation,
                action_id=action_id,
                actor=actor,
            )
        except Exception as exc:
            try:
                await interaction.followup.send(
                    f'{operation.capitalize()} failed: {exc}',
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                return
