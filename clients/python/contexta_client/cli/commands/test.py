from __future__ import annotations

import time
from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client


def test(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
    user_id: str = typer.Option("test_user", "--user-id", help="Test user ID"),
) -> None:
    """Smoke test: ping API, send observation, retrieve context."""
    client = _get_client(profile)

    typer.echo("Pinging api...")
    try:
        health = client.ping()
        typer.echo(f"API reachable: {health}")
    except Exception as e:
        typer.echo(f"Ping failed: {e}")
        raise typer.Exit(1)

    typer.echo("Sending sample observation...")
    try:
        resp = client.observe(
            user_id=user_id,
            messages=[
                {"role": "user", "content": "Hello, this is a test observation."},
                {"role": "assistant", "content": "Test recorded."},
            ],
        )
        typer.echo(f"Accepted (job_id {resp.job_id})")
    except Exception as e:
        typer.echo(f"Observation failed: {e}")
        raise typer.Exit(1)

    typer.echo("Waiting for extraction...")
    time.sleep(2)

    typer.echo("Retrieving context...")
    try:
        ctx = client.context(user_id=user_id, token_budget=500)
        memory_count = len(ctx.relevant_memories)
        typer.echo(f"Got context with {memory_count} memories")
    except Exception as e:
        typer.echo(f"Context retrieval failed: {e}")
        raise typer.Exit(1)

    typer.echo("contexta is working.")
