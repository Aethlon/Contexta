"""SQLAlchemy models for the contexta memory engine.

All models use shared-table multi-tenancy with organization_id column
for tenant isolation.
"""

from contexta.models.account import Account, Organization, OrganizationMember, Project
from contexta.models.api_key import ApiKeyRecord
from contexta.models.artifact import Artifact, ArtifactRecord
from contexta.models.audit import AuditLog
from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from contexta.models.block import (
    Block,
    MemoryBlock,
    MemoryBlockRevision,
    MemoryBlockVersion,
)
from contexta.models.consolidation import ConsolidatedObservation
from contexta.models.dream import MissingMemoryCandidate
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.models.evidence import (
    Episode,
    ImmutableRecordError,
    MemoryEvidence,
    SourceTurn,
)
from contexta.models.fact import Fact, MemoryFact
from contexta.models.identity import Agent, MemoryUser, SessionScope
from contexta.models.ingestion import (
    IngestionAttempt,
    IngestionDeadLetter,
    IngestionObservation,
    IngestionOutboxEvent,
    IngestionSourceTurn,
)
from contexta.models.memory import MemoryRecord
from contexta.models.proposal import (
    AdmissionState,
    MemoryProposal,
    ProposalType,
    ProposalValidationState,
    RiskTier,
)
from contexta.models.session import Session
from contexta.models.version import MemoryVersion

__all__ = [
    "Account",
    "AdmissionState",
    "Agent",
    "ApiKeyRecord",
    "Artifact",
    "ArtifactRecord",
    "AuditLog",
    "Base",
    "Block",
    "ConsolidatedObservation",
    "Entity",
    "EntityEdge",
    "Episode",
    "Fact",
    "ImmutableRecordError",
    "IngestionAttempt",
    "IngestionDeadLetter",
    "IngestionObservation",
    "IngestionOutboxEvent",
    "IngestionSourceTurn",
    "MemoryBlock",
    "MemoryBlockRevision",
    "MemoryBlockVersion",
    "MemoryEntityLink",
    "MemoryEvidence",
    "MemoryFact",
    "MemoryProposal",
    "MemoryRecord",
    "MemoryUser",
    "MemoryVersion",
    "MissingMemoryCandidate",
    "Organization",
    "OrganizationMember",
    "Project",
    "ProposalType",
    "ProposalValidationState",
    "RiskTier",
    "Session",
    "SessionScope",
    "SourceTurn",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
