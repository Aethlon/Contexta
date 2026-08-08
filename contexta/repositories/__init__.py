"""Data access layer with tenant-scoped repositories.

All repositories enforce organization_id isolation on every query,
implementing shared-table multi-tenancy at the data access layer.
"""

from contexta.repositories.api_key_repo import ApiKeyRepository
from contexta.repositories.audit_repo import AuditRepository
from contexta.repositories.base import TenantScopedRepository
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.repositories.session_repo import SessionRepository
from contexta.repositories.version_repo import MemoryVersionRepository

__all__ = [
    "ApiKeyRepository",
    "AuditRepository",
    "EntityEdgeRepository",
    "EntityRepository",
    "MemoryEntityLinkRepository",
    "MemoryRepository",
    "MemoryVersionRepository",
    "SessionRepository",
    "TenantScopedRepository",
]
