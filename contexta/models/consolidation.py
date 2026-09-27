from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from contexta.models.proposal import AdmissionState, ProposalType, ProposalValidationState, RiskTier


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ConsolidatedObservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consolidated_observation"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProposalType.FACT.value
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_tier: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RiskTier.LOW.value
    )
    admission_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AdmissionState.REVIEW.value
    )
    validation_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProposalValidationState.PENDING.value
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staged")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    supporting_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    source_observation_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    fact_keys: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)), nullable=False, default=list
    )
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    applied_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_record.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_consolidated_observation_org_idempotency",
        ),
        Index("ix_consolidated_observation_org_id", "organization_id"),
        Index(
            "ix_consolidated_observation_org_user_state",
            "organization_id",
            "user_id",
            "validation_state",
        ),
        Index(
            "ix_consolidated_observation_supporting_ids",
            "supporting_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_consolidated_observation_evidence_ids",
            "evidence_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_consolidated_observation_fact_keys",
            "fact_keys",
            postgresql_using="gin",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:
        aliases = {
            "text": "content",
            "observation": "content",
            "evidence": "evidence_refs",
            "fact_references": "fact_keys",
            "supporting_memory_ids": "supporting_ids",
            "evidence_memory_ids": "evidence_ids",
            "validation_status": "validation_state",
        }
        for alias, target in aliases.items():
            if alias in kwargs:
                value = kwargs.pop(alias)
                kwargs.setdefault(target, value)
        for field_name in (
            "evidence_ids",
            "supporting_ids",
            "source_observation_ids",
            "fact_keys",
            "evidence_refs",
        ):
            value = kwargs.get(field_name)
            if value is not None and not isinstance(value, list):
                kwargs[field_name] = list(value)
        for field_name in ("observation_type", "risk_tier", "admission_state", "validation_state"):
            value = kwargs.get(field_name)
            if isinstance(value, Enum):
                kwargs[field_name] = value.value
        super().__init__(**kwargs)

    @property
    def text(self) -> str:
        return self.content

    @property
    def observation(self) -> str:
        return self.content

    @property
    def evidence(self) -> list[dict[str, Any]]:
        return self.evidence_refs

    @property
    def fact_references(self) -> list[str]:
        return self.fact_keys

    @property
    def supporting_memory_ids(self) -> list[uuid.UUID]:
        return self.supporting_ids

    @property
    def validation_status(self) -> str:
        return self.validation_state


__all__ = ["ConsolidatedObservation"]
