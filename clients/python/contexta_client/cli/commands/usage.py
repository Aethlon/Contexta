from __future__ import annotations

from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client


def usage(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Show current period usage."""
    client = _get_client(profile)
    data = client._http._request(method="GET", endpoint="/usage")
    plan = data.get("plan", "unknown")
    period = data.get("period", {})
    limits = data.get("limits", {})
    consumed = data.get("consumed", {})
    cost = data.get("cost_estimate_cents", 0)

    typer.echo(f"Plan: {plan}")
    typer.echo(f"Period: {period.get('start', '?')} to {period.get('end', '?')}")
    for key in limits:
        used = consumed.get(key, 0)
        lim = limits.get(key, 0)
        pct = (used / lim * 100) if lim else 0
        typer.echo(f"  {key:20} {used:>10,} / {lim:<10,} ({pct:.1f}%)")
    typer.echo(f"Estimated cost: ${cost / 100:.2f}")


def audit(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Tail audit log"),
) -> None:
    """Tail audit log."""
    client = _get_client(profile)
    data = client._http._request(method="GET", endpoint="/audit")
    items = data if isinstance(data, list) else data.get("events", data.get("data", []))
    for ev in items:
        ts = ev.get("timestamp", ev.get("created_at", ""))
        op = ev.get("operation_type", ev.get("action", ""))
        actor = ev.get("actor_id", ev.get("user_id", ""))
        typer.echo(f"{ts}  {op:20}  {actor}")


def export_data(
    user_id: str = typer.Option(..., "--user-id", help="User ID"),
    output: str = typer.Option("memories.jsonl", "--output", "-o", help="Output file"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Export memories to JSONL."""
    client = _get_client(profile)
    memories = client.retrieve(user_id=user_id, query_text="*", limit=1000)
    with open(output, "w") as f:
        for m in memories:
            f.write(m.model_dump_json(exclude_none=True) + "\n")
    typer.echo(f"Exported {len(memories)} memories to {output}")
