from __future__ import annotations

from pathlib import Path

import typer


def init(
    directory: str = typer.Argument(".", help="Directory to scaffold"),
) -> None:
    """Scaffold .env, integration snippet, and recommended SDK install."""
    target = Path(directory).resolve()
    target.mkdir(parents=True, exist_ok=True)

    env_file = target / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# contexta Configuration\n"
            "# Get your API key at https://dashboard.contexta.dev\n"
            "CONTEXTA_API_KEY=mk_live_\n"
            "CONTEXTA_API_URL=https://api.contexta.dev/v1\n"
            "CONTEXTA_ORGANIZATION_ID=\n"
            "CONTEXTA_TIMEOUT_MS=30000\n"
            "CONTEXTA_MAX_RETRIES=3\n"
            "CONTEXTA_TELEMETRY=true\n"
            "CONTEXTA_VERIFY_TLS=true\n"
            "CONTEXTA_CA_BUNDLE=\n"
        )
        typer.echo(f"Created {env_file}")
    else:
        typer.echo(f"{env_file} already exists, skipping.")

    example_file = target / "CONTEXTA_example.py"
    if not example_file.exists():
        example_file.write_text(
            '"""contexta quickstart example."""\n'
            "import os\n"
            "from uuid import uuid4\n\n"
            "from contexta_client import Contexta\n\n"
            'm = Contexta.from_env()\n'
            'user_id = os.environ.get("CONTEXTA_USER_ID", str(uuid4()))\n'
            'organization_id = os.environ.get("CONTEXTA_ORGANIZATION_ID", str(uuid4()))\n'
            'session_id = str(uuid4())\n\n'
            "# Send an observation\n"
            "resp = m.observe(\n"
            "    user_id=user_id,\n"
            "    session_id=session_id,\n"
            "    messages=[\n"
            '        {"role": "user", "content": "I prefer Postgres over Mongo."},\n'
            '        {"role": "assistant", "content": "Noted."},\n'
            "    ],\n"
            '    policy="default",\n'
            ")\n"
            'print(f"Observation accepted: {resp.job_id}")\n\n'
            "# Retrieve context\n"
            "ctx = m.context(\n"
            "    user_id=user_id,\n"
            "    organization_id=organization_id,\n"
            "    session_id=session_id,\n"
            "    token_budget=1500,\n"
            ")\n"
            "print(ctx.to_system_prompt())\n"
            "m.close()\n"
        )
        typer.echo(f"Created {example_file}")
    else:
        typer.echo(f"{example_file} already exists, skipping.")

    typer.echo("\nRun: pip install contexta-client && python CONTEXTA_example.py")
