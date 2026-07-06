"""SQLAlchemy models for the contexta memory engine.

All models use shared-table multi-tenancy with organization_id column
for tenant isolation.
"""

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from contexta.models.api_key import ApiKeyRecord
from contexta.models.audit import AuditLog
from contexta.models.cluster import ClusterMembership, SemanticCluster
from contexta.models.compression import CompressedSummary
from contexta.models.dream import MissingMemoryCandidate
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.models.feedback import RetrievalFeedback
from contexta.models.memory import MemoryRecord
from contexta.models.policy import MemoryPolicy
from contexta.models.schema import CustomSchema
from contexta.models.session import Session
from contexta.models.version import MemoryVersion
from contexta.models.account import Account, Organization, OrganizationMember, Project
from contexta.models.usage import UsageEvent, UsageDaily, UsagePeriod

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "Account",
    "Organization",
    "OrganizationMember",
    "Project",
    "UsageEvent",
    "UsageDaily",
    "UsagePeriod",
    "ApiKeyRecord",
    "AuditLog",
    "ClusterMembership",
    "CompressedSummary",
    "CustomSchema",
    "Entity",
    "EntityEdge",
    "MemoryEntityLink",
    "MemoryPolicy",
    "MemoryRecord",
    "MemoryVersion",
    "MissingMemoryCandidate",
    "RetrievalFeedback",
    "SemanticCluster",
    "Session",
]
