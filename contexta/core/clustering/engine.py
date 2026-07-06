"""Semantic cluster engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from contexta.models.cluster import ClusterMembership, SemanticCluster


class SemanticClusterEngine:
    """Create and maintain clusters with at least three members."""

    MIN_MEMBERS = 3

    def create_cluster(self, *, organization_id: uuid.UUID, user_id: uuid.UUID, name: str, memory_ids: list[uuid.UUID]) -> tuple[SemanticCluster | None, list[ClusterMembership]]:
        if len(memory_ids) < self.MIN_MEMBERS:
            return None, []
        cluster = SemanticCluster(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            name=name,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        memberships = [
            ClusterMembership(cluster_id=cluster.id, memory_id=memory_id)
            for memory_id in memory_ids
        ]
        return cluster, memberships

    def should_dissolve(self, member_count: int) -> bool:
        return member_count < self.MIN_MEMBERS
