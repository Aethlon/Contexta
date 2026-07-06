"""Usage event, daily rollup, and billing period models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base


class UsageEvent(Base):
    __tablename__ = "usage_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    api_key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = {
        "postgresql_partition_by": "RANGE (occurred_at)",
    }


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    classification: Mapped[str] = mapped_column(String(50), primary_key=True, nullable=False)
    units: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    llm_tokens_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    llm_tokens_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    request_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


class UsagePeriod(Base):
    __tablename__ = "usage_period"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    observations: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    retrievals: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reranks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    memory_writes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    active_memories: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    overage_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
