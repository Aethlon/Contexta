"""Account, Organization, OrganizationMember, and Project models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Account(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "account"

    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oauth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="account", lazy="selectin"
    )


class Organization(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    dodo_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dodo_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization", lazy="selectin"
    )
    projects: Mapped[list[Project]] = relationship(back_populates="organization", lazy="selectin")


class OrganizationMember(Base):
    __tablename__ = "organization_member"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="members")
    account: Mapped[Account] = relationship(back_populates="memberships")


class Project(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "project"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(50), default="us-east-1", nullable=False)
    hard_cap: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_project_org_slug"),
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
