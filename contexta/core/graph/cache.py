"""High-speed graph adjacency cache and sub-millisecond BFS traversal.

Provides in-memory and Redis-backed graph traversal to execute multi-hop
candidate expansion in <2ms, bypassing repeated relational SQL joins.
"""

from __future__ import annotations

import collections
import json
import logging
import uuid
from collections.abc import Sequence
from typing import Any

from contexta.models.entity import EntityEdge

logger = logging.getLogger(__name__)


class GraphCache:
    """High-speed graph adjacency cache for ultra-fast neighbor traversals."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client
        # In-memory adjacency map: user_id -> {node_id -> set of neighbor_ids}
        self._local_adj: dict[uuid.UUID, dict[uuid.UUID, set[uuid.UUID]]] = collections.defaultdict(
            lambda: collections.defaultdict(set)
        )

    def update_edges(self, user_id: uuid.UUID, edges: Sequence[EntityEdge]) -> None:
        """Add edges to the in-memory graph cache and synchronously sync to Redis."""
        user_adj = self._local_adj[user_id]
        redis_pipe = self._redis.pipeline() if self._redis is not None else None

        for edge in edges:
            s, t = edge.source_entity_id, edge.target_entity_id
            user_adj[s].add(t)
            user_adj[t].add(s)

            if redis_pipe is not None:
                # Store in Redis sets: graph:{user_id}:adj:{entity_id}
                key_s = f"graph:{user_id}:adj:{s}"
                key_t = f"graph:{user_id}:adj:{t}"
                redis_pipe.sadd(key_s, str(t))
                redis_pipe.sadd(key_t, str(s))
                redis_pipe.expire(key_s, 86400)
                redis_pipe.expire(key_t, 86400)

        if redis_pipe is not None:
            try:
                redis_pipe.execute()
            except Exception as exc:
                logger.warning("Failed to sync graph edges to Redis: %s", exc)

    def get_neighbors(self, user_id: uuid.UUID, entity_id: uuid.UUID) -> set[uuid.UUID]:
        """Get 1-hop neighbors from local cache or Redis."""
        user_adj = self._local_adj.get(user_id)
        if user_adj and entity_id in user_adj:
            return set(user_adj[entity_id])

        if self._redis is not None:
            try:
                key = f"graph:{user_id}:adj:{entity_id}"
                members = self._redis.smembers(key)
                if members:
                    neighbor_ids = {uuid.UUID(m if isinstance(m, str) else m.decode()) for m in members}
                    if user_adj is not None:
                        user_adj[entity_id].update(neighbor_ids)
                    return neighbor_ids
            except Exception as exc:
                logger.warning("Redis neighbor lookup failed: %s", exc)

        return set()

    def traverse(
        self,
        user_id: uuid.UUID,
        root_ids: Sequence[uuid.UUID],
        *,
        max_hops: int = 2,
        max_nodes: int = 50,
    ) -> dict[uuid.UUID, int]:
        """Perform sub-millisecond breadth-first traversal across cached entity graph.

        Returns
        -------
        dict[uuid.UUID, int]
            Mapping of discovered entity_id -> hop distance from nearest root.
        """
        distances: dict[uuid.UUID, int] = {root: 0 for root in root_ids}
        queue: collections.deque[tuple[uuid.UUID, int]] = collections.deque((r, 0) for r in root_ids)

        while queue and len(distances) < max_nodes:
            current, dist = queue.popleft()
            if dist >= max_hops:
                continue

            neighbors = self.get_neighbors(user_id, current)
            for neighbor in neighbors:
                if neighbor not in distances:
                    distances[neighbor] = dist + 1
                    queue.append((neighbor, dist + 1))
                    if len(distances) >= max_nodes:
                        break

        return distances
