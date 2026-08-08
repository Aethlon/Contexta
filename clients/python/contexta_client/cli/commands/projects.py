from __future__ import annotations

from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client, _load_config, _save_config, CONFIG_DIR, CONFIG_FILE


def list_projects(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """List your projects."""
    client = _get_client(profile)
    data = client._http._request(method="GET", endpoint="/projects")
    items = data if isinstance(data, list) else data.get("projects", data.get("data", []))
    for p in items:
        pid = p.get("project_id", p.get("id", ""))[:8]
        name = p.get("name", "")
        typer.echo(f"{pid:8}  {name}")


def create_project(
    name: str = typer.Option(..., "--name", help="Project name"),
    description: Optional[str] = typer.Option(None, "--description", help="Project description"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Create a new project."""
    client = _get_client(profile)
    body = {"name": name}
    if description:
        body["description"] = description
    data = client._http._request(method="POST", endpoint="/projects", body=body, is_write=True)
    typer.echo(f"Created project '{name}' (id {data.get('project_id', data.get('id', ''))})")


def use_project(
    project_id: str = typer.Argument(..., help="Project ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Set the default project for subsequent commands."""
    config = _load_config()
    section = f"profiles.{profile}" if profile != "default" else "default"
    if section not in config:
        typer.echo(f"Profile '{profile}' not configured.")
        raise typer.Exit(1)
    config[section]["project_id"] = project_id
    _save_config(config)
    typer.echo(f"Default project set to {project_id} for profile '{profile}'.")
