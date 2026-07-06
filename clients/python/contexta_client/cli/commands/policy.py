from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml

from contexta_client.cli.commands.login import _get_client


def list_policies(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """List policies."""
    client = _get_client(profile)
    policies = client.list_policies()
    for p in policies:
        typer.echo(f"{p.policy_id[:8] if p.policy_id else '':8}  {p.name}")


def show_policy(
    name: str = typer.Argument(..., help="Policy name"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Show a policy."""
    client = _get_client(profile)
    policies = client.list_policies()
    for p in policies:
        if p.name == name:
            typer.echo(p.model_dump_json(indent=2))
            return
    typer.echo(f"Policy '{name}' not found.")


def create_policy(
    name: str = typer.Option(..., "--name", help="Policy name"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="YAML/JSON file"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Register a policy from a YAML/JSON file or inline."""
    client = _get_client(profile)
    if file:
        content = file.read_text(encoding="utf-8")
        data = yaml.safe_load(content) if file.suffix in (".yaml", ".yml") else json.loads(content)
        name = data.get("name", name)
        store_rules = data.get("store_rules", [])
        ignore_rules = data.get("ignore_rules", [])
        priority_weights = data.get("priority_weights", {})
    else:
        store_rules = []
        ignore_rules = []
        priority_weights = {}
    policy = client.register_policy(
        name=name,
        store_rules=store_rules,
        ignore_rules=ignore_rules,
        priority_weights=priority_weights,
    )
    typer.echo(f"Registered policy '{policy.name}' (id {policy.policy_id})")


def sync_policies(
    directory: Path = typer.Argument(..., help="Directory with YAML policy files", exists=True, file_okay=False),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Sync policies from a directory."""
    client = _get_client(profile)
    for f in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        policy = client.register_policy(
            name=data.get("name", f.stem),
            store_rules=data.get("store_rules", []),
            ignore_rules=data.get("ignore_rules", []),
            priority_weights=data.get("priority_weights", {}),
        )
        typer.echo(f"Synced '{policy.name}' (id {policy.policy_id})")
