#!/usr/bin/env python3
"""Create your first Contexta organization and API key.

Why this exists
---------------
``POST /v1/keys`` is itself authenticated, so a brand-new install has no way to
mint its own first key over HTTP. Historically the README told you to hand-write
a SQL ``INSERT`` and compute a SHA-256 by hand. This does it in one command.

It is idempotent: re-running with the same ``--org``/``--user`` labels reuses the
existing rows instead of creating duplicates, so it is safe to run again.

Usage
-----
    python scripts/bootstrap_key.py                       # first run
    python scripts/bootstrap_key.py --name my-laptop      # name the key
    python scripts/bootstrap_key.py --org-name "Acme"     # reuse/label a tenant
    python scripts/bootstrap_key.py --print-env           # also emit .env lines

Nothing here is a secret-handling problem: the token is generated here, shown
once, and only its SHA-256 hash is ever stored.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "contexta"


def find_postgres_container() -> str:
    """Return the postgres container that actually holds the Contexta database.

    Matching on the substring "postgres" alone is not safe: a developer machine
    often has several projects' Postgres containers running at once, and picking
    the wrong one fails with a confusing "database does not exist". So we probe
    each candidate and require the ``contexta`` database to be present.
    """
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(
            "Could not talk to Docker. Is the stack running?\n"
            "  Start it with:  docker compose up -d"
        )

    candidates = [n for n in result.stdout.split() if "postgres" in n]
    if not candidates:
        sys.exit("No running container matched 'postgres'. Is the stack up?  docker compose up -d")

    for name in candidates:
        probe = subprocess.run(
            ["docker", "exec", name, "psql", "-U", "postgres", "-lqt"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0 and re.search(r"^\s*contexta\s*\|", probe.stdout, re.M):
            return name

    sys.exit(
        "Found a Postgres container, but none of them has a 'contexta' database.\n"
        f"  Candidates: {', '.join(candidates)}\n"
        "  The stack may not have finished its first-boot migration yet.\n"
        "  Check:  docker compose logs migration"
    )


def psql(container: str, sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "contexta",
         "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit("psql failed:\n" + (result.stderr or result.stdout)[:800])
    return (result.stdout or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="first-key", help="label for the API key")
    parser.add_argument("--org-name", default="My Contexta", help="organization display name")
    parser.add_argument("--user-name", default="local-operator", help="actor display name")
    parser.add_argument("--org", default=None, help="reuse an existing organization UUID")
    parser.add_argument("--user", default=None, help="reuse an existing actor UUID")
    parser.add_argument("--print-env", action="store_true",
                        help="also print ready-to-paste .env lines")
    args = parser.parse_args()

    container = find_postgres_container()
    org_id = args.org
    user_id = args.user
    account_id: str | None = None

    # These mirror exactly what POST /v1/auth/signup creates: an account, an
    # organization, and an owner membership. We deliberately do not create a
    # memory_user row — signup does not, and the actor identity is carried by
    # the API key itself, so a request's user_id simply has to match it.
    slug = slugify(args.org_name)
    email = f"{slug}@localhost"

    if org_id is None:
        existing = psql(
            container,
            f"SELECT id FROM organization WHERE slug = '{slug}' LIMIT 1;",
        )
        if existing:
            org_id = existing.splitlines()[0].strip()
            print(f"Reusing organization {org_id} (slug: {slug})")
        else:
            org_id = str(uuid.uuid4())
            psql(
                container,
                "INSERT INTO organization (id, name, slug, plan_code, status, "
                "created_at, updated_at) "
                f"VALUES ('{org_id}', '{args.org_name}', '{slug}', 'sovereign', "
                "'active', now(), now());",
            )
            print(f"Created organization {org_id} (slug: {slug})")

    existing_account = psql(
        container,
        f"SELECT id FROM account WHERE email = '{email}' LIMIT 1;",
    )
    if existing_account:
        account_id = existing_account.splitlines()[0].strip()
        print(f"Reusing account      {account_id}")
    else:
        account_id = str(uuid.uuid4())
        psql(
            container,
            "INSERT INTO account (id, email, display_name, status, created_at, updated_at) "
            f"VALUES ('{account_id}', '{email}', '{args.user_name}', 'active', now(), now());",
        )
        print(f"Created account      {account_id} ({email})")

    psql(
        container,
        "INSERT INTO organization_member (organization_id, account_id, role, created_at) "
        f"VALUES ('{org_id}', '{account_id}', 'owner', now()) "
        "ON CONFLICT (organization_id, account_id) DO NOTHING;",
    )

    if user_id is None:
        # The actor identity is independent of the account row; it is what every
        # request's user_id must equal. Reuse the account id so one key maps to
        # exactly one (organization, actor) pair.
        user_id = account_id
    print(f"Using actor          {user_id}")

    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    prefix = token[:16]

    psql(
        container,
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', '{args.name}', '{prefix}', '{token_hash}', "
        f"'{org_id}', '{user_id}', ARRAY['read','write'], now());",
    )

    print()
    print("=" * 62)
    print("  API key created. It is shown once and cannot be recovered.")
    print("=" * 62)
    print(f"  CONTEXTA_API_KEY={token}")
    print(f"  ORG   = {org_id}")
    print(f"  ACTOR = {user_id}")
    print()
    print("  Next:")
    print("   1. add the key to your .env as CONTEXTA_DASHBOARD_API_KEY")
    print("      so the operator console can resolve its tenant, then")
    print("      docker compose up -d   and open http://localhost:3000")
    print("   2. for MCP (Claude Desktop / Cursor / Windsurf) also add it as")
    print("      CONTEXTA_MCP_API_KEY — the MCP server refuses to start without one")
    print("   3. call the API:")
    print(f'      curl -H "x-api-key: {token}" http://localhost:8000/v1/memories')

    if args.print_env:
        print()
        print("--- paste into .env ---")
        print(f"CONTEXTA_DASHBOARD_API_KEY={token}")
        print(f"CONTEXTA_MCP_API_KEY={token}")
        print(f"# CONTEXTA_DASHBOARD_ORG_ID={org_id}")
        print(f"# CONTEXTA_DASHBOARD_USER_ID={user_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
