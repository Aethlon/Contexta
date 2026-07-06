from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client


def send_observation(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Session ID"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="JSON file with observation data"),
    policy: Optional[str] = typer.Option(None, "--policy", help="Policy name"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Send a one-off observation from a JSON file or stdin."""
    client = _get_client(profile)

    if file:
        data = json.loads(file.read_text(encoding="utf-8"))
    else:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
        else:
            typer.echo("Provide observation JSON via --file or stdin.")
            raise typer.Exit(1)

    messages = data.get("messages", data.get("body", {}).get("messages", []))
    metadata = data.get("metadata")
    resp = client.observe(
        user_id=user_id,
        session_id=session_id or data.get("session_id"),
        messages=messages,
        metadata=metadata,
        policy=policy or data.get("policy"),
    )
    typer.echo(f"Observation accepted: job_id={resp.job_id}, status={resp.status}")
