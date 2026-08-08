from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import yaml

from contexta_client.cli.commands.login import _get_client


def list_schemas(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """List custom schemas."""
    client = _get_client(profile)
    data = client._http._request(method="GET", endpoint="/schemas")
    items = data if isinstance(data, list) else data.get("schemas", data.get("data", []))
    for s in items:
        typer.echo(f"{s.get('schema_id', '')[:8]:8}  {s.get('name', '')}")


def create_schema(
    file: Path = typer.Option(..., "--file", "-f", help="YAML/JSON schema definition", exists=True),
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Register a schema from a YAML/JSON file."""
    client = _get_client(profile)
    content = file.read_text(encoding="utf-8")
    data = yaml.safe_load(content) if file.suffix in (".yaml", ".yml") else json.loads(content)
    schema = client.register_schema(
        name=data.get("name", file.stem),
        fields=data.get("field_definitions", data.get("fields", [])),
    )
    typer.echo(f"Registered schema '{schema.name}' (id {schema.schema_id})")
