from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .schemas import ApprovalStatus, RunCreateRequest, RunRecord

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
    reason: str | None = None,
) -> None:
    if operation == 'approve':
        engine.approve_action(
            action_id,
            reviewer=actor.reviewer,
            reason=reason or 'Approved through Discord controls.',
        )
    elif operation == 'reject':
        engine.reject_action(
            action_id,
            reviewer=actor.reviewer,
            reason=reason or 'Rejected through Discord controls.',
        )
    else:
        raise ValueError(f'unsupported Discord operation: {operation}')


def execute_discord_run_creation(
    engine: ResearchOrchestrator,
    *,
    objective: str,
) -> RunRecord:
    return engine.create_run(RunCreateRequest(objective=objective))


def execute_discord_benchmark_creation(
    engine: ResearchOrchestrator,
    *,
    filename: str,
    content: bytes,
    objective: str | None,
) -> RunRecord:
    task = engine.task_bundles.import_archive(
        filename=filename,
        content=content,
    )
    return engine.create_run(
        RunCreateRequest(
            objective=objective
            or f'Complete and evaluate the imported {task.display_name} benchmark.',
            task_id=task.task_id,
            task_bundle_digest=task.digest,
        )
    )


class DiscordControlGateway:
    """Outbound Gateway listener for bounded approval-button interactions."""

    def __init__(
        self,
        *,
        engine: ResearchOrchestrator,
        bot_token: str,
        guild_id: str,
        channel_id: str,
        admin_role_id: str | None,
        admin_user_ids: list[str],
    ) -> None:
        self.engine = engine
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.policy = DiscordControlPolicy(
            guild_id=guild_id,
            admin_role_id=admin_role_id,
            admin_user_ids=admin_user_ids,
        )
        intents = discord.Intents.none()
        intents.guilds = True
        self.client = discord.Client(intents=intents)
        self.guild = discord.Object(id=int(guild_id))
        self.tree = app_commands.CommandTree(self.client)
        self._commands_synced = False
        self._register_commands()
        self.client.on_ready = self._on_ready
        self.client.on_interaction = self._on_interaction
        self._tasks: set[asyncio.Task[None]] = set()

    def _register_commands(self) -> None:
        @self.tree.command(
            name='research-start',
            description='Start a Glasslab research run from an objective.',
            guild=self.guild,
        )
        @app_commands.describe(
            objective=(
                'Research objective for Honeydew to turn into a protocol '
                'and evaluation contract proposal.'
            )
        )
        async def research_start(
            interaction: discord.Interaction,
            objective: app_commands.Range[str, 10, 2000],
        ) -> None:
            await self._on_research_start(
                interaction,
                objective=str(objective),
            )

        @self.tree.command(
            name='benchmark-start',
            description='Import and start a supported Glasslab ML benchmark.',
            guild=self.guild,
        )
        @app_commands.describe(
            archive='One supported ML_Benchmark_*.zip task bundle.',
            objective='Optional narrower objective for this benchmark run.',
        )
        async def benchmark_start(
            interaction: discord.Interaction,
            archive: discord.Attachment,
            objective: app_commands.Range[str, 10, 1000] | None = None,
        ) -> None:
            await self._on_benchmark_start(
                interaction,
                archive=archive,
                objective=str(objective) if objective else None,
            )

    async def _on_ready(self) -> None:
        if self._commands_synced:
            return
        await self.tree.sync(guild=self.guild)
        self._commands_synced = True

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

    async def _on_research_start(
        self,
        interaction: discord.Interaction,
        *,
        objective: str,
    ) -> None:
        actor = self._actor(interaction)
        if not self.policy.is_authorized(actor):
            await self._respond(
                interaction,
                'You are not authorized to start Glasslab research runs.',
            )
            return
        if str(interaction.channel_id) != self.channel_id:
            await self._respond(
                interaction,
                'Start research runs from the configured Glasslab channel.',
            )
            return
        await self._respond(
            interaction,
            (
                'Research request accepted. Honeydew is drafting the protocol '
                'and evaluation contract proposal; a run thread will appear '
                'in this channel.'
            ),
        )
        task = asyncio.create_task(
            self._create_run(
                interaction=interaction,
                objective=objective,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _create_run(
        self,
        *,
        interaction: discord.Interaction,
        objective: str,
    ) -> None:
        try:
            run = await asyncio.to_thread(
                execute_discord_run_creation,
                self.engine,
                objective=objective,
            )
            destination = (
                f'<#{run.discord_thread_id}>'
                if run.discord_thread_id
                else f'run `{run.run_id}`'
            )
            await interaction.followup.send(
                (
                    f'Research run created in {destination}. '
                    'Review the proposed protocol and evaluation contract there.'
                ),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            try:
                await interaction.followup.send(
                    f'Research run creation failed: {exc}',
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                return

    async def _on_benchmark_start(
        self,
        interaction: discord.Interaction,
        *,
        archive: discord.Attachment,
        objective: str | None,
    ) -> None:
        actor = self._actor(interaction)
        if not self.policy.is_authorized(actor):
            await self._respond(
                interaction,
                'You are not authorized to start Glasslab benchmark runs.',
            )
            return
        if str(interaction.channel_id) != self.channel_id:
            await self._respond(
                interaction,
                'Start benchmark runs from the configured Glasslab channel.',
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            content = await archive.read()
            run = await asyncio.to_thread(
                execute_discord_benchmark_creation,
                self.engine,
                filename=archive.filename,
                content=content,
                objective=objective,
            )
            destination = (
                f'<#{run.discord_thread_id}>'
                if run.discord_thread_id
                else f'run `{run.run_id}`'
            )
            await interaction.followup.send(
                (
                    f'Benchmark imported and started in {destination}. '
                    'Honeydew is drafting the protocol from the task and rubric.'
                ),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            await interaction.followup.send(
                f'Benchmark import or run creation failed: {exc}',
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

        if operation == 'reject':
            await interaction.response.send_modal(
                RejectActionModal(
                    gateway=self,
                    action_id=action_id,
                    actor=actor,
                )
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
                reason=None,
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
        reason: str | None,
    ) -> None:
        try:
            await asyncio.to_thread(
                execute_discord_action,
                self.engine,
                operation=operation,
                action_id=action_id,
                actor=actor,
                reason=reason,
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

    async def submit_rejection(
        self,
        *,
        interaction: discord.Interaction,
        action_id: str,
        actor: DiscordControlActor,
        reason: str,
    ) -> None:
        await self._respond(
            interaction,
            (
                'Reject request received with revision feedback. '
                'The authoritative result will be posted in this thread.'
            ),
        )
        task = asyncio.create_task(
            self._execute(
                interaction=interaction,
                operation='reject',
                action_id=action_id,
                actor=actor,
                reason=reason,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


class RejectActionModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        gateway: DiscordControlGateway,
        action_id: str,
        actor: DiscordControlActor,
    ) -> None:
        super().__init__(title='Reject research action')
        self.gateway = gateway
        self.action_id = action_id
        self.actor = actor
        self.feedback = discord.ui.TextInput(
            label='Required revision',
            style=discord.TextStyle.paragraph,
            placeholder=(
                'Describe what Honeydew or Beaker must correct before '
                'requesting approval again.'
            ),
            min_length=5,
            max_length=1000,
            required=True,
        )
        self.add_item(self.feedback)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.gateway.submit_rejection(
            interaction=interaction,
            action_id=self.action_id,
            actor=self.actor,
            reason=str(self.feedback.value).strip(),
        )
