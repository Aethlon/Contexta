"""MemoryPolicy SQLAlchemy model.

Domain-specific extraction policy configuration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MemoryPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Domain-specific extraction policy configuration."""

    __tablename__ = "memory_policy"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    store_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ignore_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    priority_weights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
