"""Read-only turn inspection: redact and bound persisted TurnRecords.

TurnRecord (schemas.py) is already durably persisted by ResearchOrchestrator
via SqliteStore/PostgresStore.save_turn — one record per Honeydew/Beaker
agent turn, with its input_event, structured_output, status, and
timestamps. This module builds the redacted, bounded view exposed through
GET /runs/{run_id}/turns and the /research-turns Discord command. It is
strictly additive: it never writes a turn, never supersedes the normalized
event log, and is read-only in the same sense as the existing
/runs/{run_id}/events and /runs/{run_id}/artifacts endpoints.
"""

from __future__ import annotations

from .redaction import redact_payload
from .schemas import AgentName, RunRecord, TurnRecord, TurnSummary

# Turns are naturally far fewer per run than events (bounded by
# Settings.maximum_turns, default 20) or artifacts, but a structured_output
# payload can be large (claims, produced files, full proposals), so the
# endpoint still bounds how many turns it returns per call rather than
# assuming the natural count is always small.
DEFAULT_TURN_LIMIT = 20
MAXIMUM_TURN_LIMIT = 100

# The Discord command renders into one ephemeral message (2000-char Discord
# ceiling), so it defaults to a much smaller window than the HTTP endpoint.
DEFAULT_DISCORD_TURN_LIMIT = 5
MAXIMUM_DISCORD_TURN_LIMIT = 20
_MAX_DETAIL_CHARS = 160
_MAX_MESSAGE_CHARS = 1800


def _turn_to_summary(turn: TurnRecord) -> TurnSummary:
    output = (
        redact_payload(turn.structured_output.model_dump(mode='json'))
        if turn.structured_output is not None
        else None
    )
    return TurnSummary(
        turn_id=turn.turn_id,
        run_id=turn.run_id,
        agent=turn.agent,
        status=turn.status,
        # error is a raw exception message (see engine._run_agent_turn's
        # failure path) and can echo back arbitrary runtime/HTTP failure
        # text, so it gets the same treatment as input/output rather than
        # being assumed safe because it isn't structured agent content.
        error=redact_payload(turn.error) if turn.error is not None else None,
        input=redact_payload(turn.input_event),
        output=output,
        started_at=turn.created_at,
        # A running turn has no end yet; updated_at only becomes meaningful
        # once the turn transitions to completed/failed/aborted.
        ended_at=turn.updated_at if turn.status != 'running' else None,
    )


def summarize_turns(
    turns: list[TurnRecord],
    *,
    limit: int = DEFAULT_TURN_LIMIT,
) -> list[TurnSummary]:
    """Redact and bound a run's turns to at most ``limit`` entries.

    ``turns`` is expected in storage order (oldest first, see
    SqliteStore.list_turns). The most recent ``limit`` turns are kept, in
    their original chronological order, so a caller reading top-to-bottom
    sees the run's actual sequence rather than a reversed one.
    """
    bounded_limit = max(1, min(limit, MAXIMUM_TURN_LIMIT))
    selected = turns[-bounded_limit:] if len(turns) > bounded_limit else turns
    return [_turn_to_summary(turn) for turn in selected]


def _truncate(text: str, *, limit: int = _MAX_DETAIL_CHARS) -> str:
    collapsed = ' '.join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + '…'


def format_turn_history(
    run: RunRecord,
    turns: list[TurnSummary],
    *,
    total_turns: int,
) -> str:
    """Render a bounded, redacted turn history for a Discord response.

    ``turns`` should already be the output of summarize_turns; ``total_turns``
    is the full (unbounded) count so a truncated view says so explicitly
    instead of silently looking complete.
    """
    if not turns:
        return f'Run `{run.run_id}` has no recorded agent turns yet.'

    lines = [
        f'Turn history for `{run.run_id}` (showing {len(turns)} of '
        f'{total_turns}, oldest first):',
    ]
    for turn in turns:
        agent_label = 'Honeydew' if turn.agent == AgentName.HONEYDEW else 'Beaker'
        kind = turn.output.get('kind') if isinstance(turn.output, dict) else None
        window = turn.started_at.isoformat()
        if turn.ended_at is not None:
            window += f' → {turn.ended_at.isoformat()}'
        detail = None
        if isinstance(turn.output, dict):
            detail = turn.output.get('summary')
        detail = detail or turn.error
        line = f'- **{agent_label}** `{turn.status}`'
        if kind:
            line += f' ({kind})'
        line += f' {window}'
        if detail:
            line += f'\n  {_truncate(str(detail))}'
        lines.append(line)

    message = '\n'.join(lines)
    if len(message) > _MAX_MESSAGE_CHARS:
        message = message[:_MAX_MESSAGE_CHARS].rstrip() + '\n… (truncated)'
    return message
