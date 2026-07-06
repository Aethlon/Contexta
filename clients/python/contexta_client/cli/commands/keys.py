from __future__ import annotations

from typing import Optional

import typer

from contexta_client.cli.commands.login import _get_client


def list_keys(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """List API keys."""
    client = _get_client(profile)
    data = client._http._request(method="GET", endpoint="/keys")
    items = data if isinstance(data, list) else data.get("keys", data.get("data", []))
    for k in items:
        key_id = k.get("key_id", k.get("id", ""))[:8]
        name = k.get("name", "")
        prefix = k.get("prefix", "")
        typer.echo(f"{key_id:8}  {name:20}  prefix={prefix}")


def create_key(
    name: str = typer.Option(..., "--name", help="Key name"),
    scopes: str = typer.Option("observations:write,retrieval:read,memories:read", "--scopes", help="Comma-separated scopes"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Create a new API key."""
    client = _get_client(profile)
    body = {
        "name": name,
        "scopes": [s.strip() for s in scopes.split(",")],
    }
    if project_id:
        body["project_id"] = project_id
    data = client._http._request(method="POST", endpoint="/keys", body=body, is_write=True)
    token = data.get("token", data.get("api_key", ""))
    typer.echo(f"Created key '{name}'")
    typer.echo(f"Token: {token}")
    typer.echo("Save this token — it will not be shown again.")


def rotate_key(
    key_id: str = typer.Argument(..., help="Key ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Rotate a key."""
    client = _get_client(profile)
    data = client._http._request(method="POST", endpoint=f"/keys/{key_id}/rotate", is_write=True)
    token = data.get("token", data.get("api_key", ""))
    typer.echo(f"Rotated key {key_id}")
    typer.echo(f"New token: {token}")
    typer.echo("Old key remains valid for 24 hours.")


def revoke_key(
    key_id: str = typer.Argument(..., help="Key ID"),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Revoke a key."""
    client = _get_client(profile)
    client._http._request(method="DELETE", endpoint=f"/keys/{key_id}", is_write=True)
    typer.echo(f"Revoked key {key_id}")
