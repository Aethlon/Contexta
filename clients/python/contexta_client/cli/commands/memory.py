from __future__ import annotations

import json
from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client


def list_memories(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    limit: int = typer.Option(20, "--limit", help="Max memories"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """List memories for a user."""
    client = _get_client(profile)
    memories = client.retrieve(user_id=user_id, query_text="*", limit=limit)
    for m in memories:
        typer.echo(f"{m.memory_id[:8]}  [{m.memory_type:15}]  {m.title or '(no title)'}  score={m.score:.3f}")


def show_memory(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Show a memory."""
    client = _get_client(profile)
    mem = client.get_memory(memory_id)
    typer.echo(mem.model_dump_json(indent=2))


def explain_memory(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Show explainability for a memory."""
    client = _get_client(profile)
    explanation = client.explain(memory_id)
    typer.echo(explanation.model_dump_json(indent=2, exclude_none=True))


def pin_memory(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Pin a memory."""
    client = _get_client(profile)
    mem = client.pin(memory_id)
    typer.echo(f"Pinned {mem.memory_id}")


def archive_memory(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Archive a memory."""
    client = _get_client(profile)
    mem = client.archive(memory_id)
    typer.echo(f"Archived {mem.memory_id}")


def delete_memory(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Delete a memory (with confirm)."""
    if not force:
        confirm = typer.confirm(f"Delete memory {memory_id}?")
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(0)
    client = _get_client(profile)
    client.delete(memory_id)
    typer.echo(f"Deleted {memory_id}")
