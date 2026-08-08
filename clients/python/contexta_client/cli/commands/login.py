from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Optional

import typer

CONFIG_DIR = Path.home() / ".contexta"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def _load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        config.read(str(CONFIG_FILE))
    return config


def _save_config(config: configparser.ConfigParser) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


def _get_client(profile: str = "default"):
    from contexta_client.client import contexta
    config = _load_config()
    section = f"profiles.{profile}" if profile != "default" else "default"
    if section not in config:
        typer.echo(f"Profile '{profile}' not configured. Run 'contexta login' first.")
        raise typer.Exit(1)
    cfg = config[section]
    api_key = cfg.get("api_key") or os.environ.get("CONTEXTA_API_KEY")
    api_url = cfg.get("api_url") or os.environ.get("CONTEXTA_API_URL", "https://api.contexta.dev/v1")
    if not api_key:
        typer.echo("No API key found. Run 'contexta login' or set CONTEXTA_API_KEY.")
        raise typer.Exit(1)
    return contexta(api_key=api_key, base_url=api_url)


def login(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Authenticate and save credentials to ~/.contexta/config.toml."""
    api_key = typer.prompt("Enter your contexta API key", hide_input=True)
    api_url = typer.prompt("API URL", default="https://api.contexta.dev/v1")
    org_id = typer.prompt("Organization ID (optional)", default="")
    project_id = typer.prompt("Project ID (optional)", default="")

    config = _load_config()
    section = f"profiles.{profile}" if profile != "default" else "default"
    config[section] = {
        "api_url": api_url,
        "api_key": api_key,
    }
    if org_id:
        config[section]["org_id"] = org_id
    if project_id:
        config[section]["project_id"] = project_id
    _save_config(config)
    typer.echo(f"Logged in to profile '{profile}'.")


def logout(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Clear stored credentials."""
    config = _load_config()
    section = f"profiles.{profile}" if profile != "default" else "default"
    if section in config:
        del config[section]
        _save_config(config)
        typer.echo(f"Logged out of profile '{profile}'.")
    else:
        typer.echo(f"Profile '{profile}' not found.")


def whoami(
    profile: str = typer.Option("default", "--profile", help="Profile name"),
) -> None:
    """Print the active org, project, and key."""
    config = _load_config()
    section = f"profiles.{profile}" if profile != "default" else "default"
    if section not in config:
        typer.echo("Not logged in. Run 'contexta login'.")
        raise typer.Exit(1)
    cfg = config[section]
    api_key = cfg.get("api_key", "")
    typer.echo(f"API URL:  {cfg.get('api_url', 'not set')}")
    typer.echo(f"API Key:  {api_key[:16]}...{api_key[-4:] if len(api_key) > 20 else ''}")
    typer.echo(f"Org ID:   {cfg.get('org_id', 'not set')}")
    typer.echo(f"Project:  {cfg.get('project_id', 'not set')}")
