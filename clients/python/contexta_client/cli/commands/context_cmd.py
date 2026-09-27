from __future__ import annotations

from uuid import uuid4

import typer

from contexta_client.cli.commands.login import _get_client


def _resolve_session_id(session_id: str | None) -> str:
    return session_id or str(uuid4())


def get_context(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    session_id: str | None = typer.Option(None, "--session-id", help="Session ID (generated if omitted)"),
    organization_id: str | None = typer.Option(None, "--organization-id", help="Organization ID"),
    token_budget: int = typer.Option(2000, "--token-budget", help="Token budget"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Get context bundle for a user."""
    client = _get_client(profile)
    ctx = client.context(
        user_id=user_id,
        organization_id=organization_id,
        session_id=_resolve_session_id(session_id),
        token_budget=token_budget,
    )
    typer.echo(ctx.to_system_prompt())


def preview_context(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    session_id: str | None = typer.Option(None, "--session-id", help="Session ID (generated if omitted)"),
    organization_id: str | None = typer.Option(None, "--organization-id", help="Organization ID"),
    token_budget: int = typer.Option(2000, "--token-budget", help="Token budget"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Preview the shape and size of a context bundle."""
    client = _get_client(profile)
    ctx = client.context(
        user_id=user_id,
        organization_id=organization_id,
        session_id=_resolve_session_id(session_id),
        token_budget=token_budget,
    )
    sections = [
        f"Rules: {len(ctx.rules)}",
        f"Projects: {len(ctx.active_projects)}",
        f"Preferences: {len(ctx.preferences)}",
        f"Goals: {len(ctx.goals)}",
        f"Recent Events: {len(ctx.recent_events)}",
        f"Relevant Memories: {len(ctx.relevant_memories)}",
    ]
    if ctx.token_usage:
        sections.append(f"Token Usage: {ctx.token_usage.total}")
    sections.append(f"Cache Hit: {ctx.cache_hit}")
    typer.echo(" | ".join(sections))
    typer.echo("---")
    typer.echo(ctx.to_system_prompt())
