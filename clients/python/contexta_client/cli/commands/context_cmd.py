from __future__ import annotations

from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client


def get_context(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    token_budget: int = typer.Option(2000, "--token-budget", help="Token budget"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Get context bundle for a user."""
    client = _get_client(profile)
    ctx = client.context(
        user_id=user_id,
        session_id=session_id,
        token_budget=token_budget,
    )
    typer.echo(ctx.to_system_prompt())


def preview_context(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    query: Optional[str] = typer.Option(None, "--query", help="Sample query for ranking"),
    token_budget: int = typer.Option(2000, "--token-budget", help="Token budget"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Preview context with a sample query."""
    client = _get_client(profile)
    ctx = client.context(
        user_id=user_id,
        session_id=session_id,
        query=query,
        token_budget=token_budget,
    )
    sections = []
    if ctx.user_profile:
        sections.append(f"User Profile: {ctx.user_profile.name}")
    sections.append(f"Projects: {len(ctx.active_projects)}")
    sections.append(f"Preferences: {len(ctx.preferences)}")
    sections.append(f"Goals: {len(ctx.goals)}")
    sections.append(f"Recent Events: {len(ctx.recent_events)}")
    sections.append(f"Relevant Memories: {len(ctx.relevant_memories)}")
    if ctx.token_usage:
        sections.append(f"Token Usage: {ctx.token_usage.total}")
    sections.append(f"Cache Hit: {ctx.cache_hit}")
    typer.echo(" | ".join(sections))
    typer.echo("---")
    typer.echo(ctx.to_system_prompt())
