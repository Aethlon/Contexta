from __future__ import annotations

import typer

from contexta_client.cli.commands import (
    context_cmd,
    init,
    keys,
    login,
    memory,
    observations,
    policy,
    projects,
    schema,
    test,
    usage,
)

app = typer.Typer(
    name="contexta",
    help="contexta CLI — manage your memory layer from the terminal.",
    no_args_is_help=True,
)

app.command()(login.login)
app.command()(login.logout)
app.command()(login.whoami)
app.command()(init.init)
app.command()(test.test)

projects_app = typer.Typer(name="projects", help="Manage projects")
app.add_typer(projects_app)
projects_app.command("list")(projects.list_projects)
projects_app.command("create")(projects.create_project)
projects_app.command("use")(projects.use_project)

keys_app = typer.Typer(name="keys", help="Manage API keys")
app.add_typer(keys_app)
keys_app.command("list")(keys.list_keys)
keys_app.command("create")(keys.create_key)
keys_app.command("rotate")(keys.rotate_key)
keys_app.command("revoke")(keys.revoke_key)

policies_app = typer.Typer(name="policies", help="Manage policies")
app.add_typer(policies_app)
policies_app.command("list")(policy.list_policies)
policies_app.command("show")(policy.show_policy)
policies_app.command("create")(policy.create_policy)
policies_app.command("sync")(policy.sync_policies)

schemas_app = typer.Typer(name="schemas", help="Manage custom schemas")
app.add_typer(schemas_app)
schemas_app.command("list")(schema.list_schemas)
schemas_app.command("create")(schema.create_schema)

memories_app = typer.Typer(name="memories", help="Manage memories")
app.add_typer(memories_app)
memories_app.command("list")(memory.list_memories)
memories_app.command("show")(memory.show_memory)
memories_app.command("explain")(memory.explain_memory)
memories_app.command("pin")(memory.pin_memory)
memories_app.command("archive")(memory.archive_memory)
memories_app.command("delete")(memory.delete_memory)

observations_app = typer.Typer(name="observations", help="Send observations")
app.add_typer(observations_app)
observations_app.command("send")(observations.send_observation)

context_app = typer.Typer(name="context", help="Get context bundles")
app.add_typer(context_app)
context_app.command("get")(context_cmd.get_context)
context_app.command("preview")(context_cmd.preview_context)

app.command()(usage.usage)
app.command()(usage.audit)
app.command()(usage.export_data)

if __name__ == "__main__":
    app()
