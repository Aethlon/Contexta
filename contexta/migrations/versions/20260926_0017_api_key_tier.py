"""add api_key.tier

The rate limiter selects limits by tier, but `api_key` had no `tier` column: the
Redis publish hard-coded "standard" and the retired Go gateway looked up a tier map
that never contained it. So every key was metered as a single hard-coded tier.

Revision ID: 017
Revises: 016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

TIERS = ("hobby", "solo_pro", "team", "scale", "standard")


def upgrade() -> None:
    op.add_column(
        "api_key",
        sa.Column("tier", sa.String(32), nullable=False, server_default="standard"),
    )
    op.create_check_constraint(
        "ck_api_key_tier",
        "api_key",
        sa.text("tier IN ('hobby', 'solo_pro', 'team', 'scale', 'standard')"),
    )


def downgrade() -> None:
    op.execute(f'ALTER TABLE api_key DROP CONSTRAINT "{_tier_constraint_name()}"')
    op.drop_column("api_key", "tier")


def _tier_constraint_name() -> str:
    """The name `upgrade()` actually created, which is not the one it asked for.

    `create_check_constraint` is called with the already-prefixed
    `ck_api_key_tier`, and the Base metadata naming convention is
    `ck_%(table_name)s_%(constraint_name)s`, so PostgreSQL stored
    `ck_api_key_ck_api_key_tier`. Two consequences: dropping the literal name
    raised UndefinedObjectError, and `op.drop_constraint` cannot be used to
    repair it because the op re-applies the same convention to whatever name it
    is handed, yielding `ck_api_key_ck_api_key_ck_api_key_tier`. So the name is
    resolved from the live catalog and dropped as raw DDL. `upgrade()` is
    unchanged.
    """
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_check_constraints("api_key"):
        definition = " ".join(str(constraint.get("sqltext") or "")).casefold()
        if "tier" in constraint["name"] or "tier" in definition:
            return str(constraint["name"])
    return "ck_api_key_ck_api_key_tier"
