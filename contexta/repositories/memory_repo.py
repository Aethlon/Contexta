"""Memory repository with tenant-scoped data access.

Provides CRUD and query operations for MemoryRecord, always enforcing
organization_id isolation at the data access layer.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm.attributes import set_committed_value

from contexta.config.settings import (
    EMBEDDING_PROFILE_ALIASES,
    OFFLINE_EMBEDDING_PROFILE,
    ONLINE_EMBEDDING_PROFILE,
    EmbeddingProfile,
    get_settings,
)
from contexta.core.crypto.vault import encrypt_content
from contexta.core.errors import AuthorizationError
from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryState, MemoryType
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.models.memory import MemoryRecord
from contexta.repositories.base import TenantScopedRepository

# pgvector explores at most hnsw.ef_search candidates per query, so never
# configure a breadth below the engine default of 40.
HNSW_EF_SEARCH_FLOOR = 40

# Columns that carry a memory's identity or the validity window of its claim.
# A write touching any of them is checked against the stored row first.
_IDENTITY_COLUMNS = frozenset({"fact_key", "valid_from", "valid_to"})


class MemoryFactKeyMutationError(ValueError):
    """Raised when a caller tries to re-point a memory at another fact slot."""


class MemoryRepository(TenantScopedRepository["MemoryRecord"]):
    """Tenant-scoped repository for MemoryRecord operations."""

    _DEFAULT_PAGE_LIMIT = 100
    _MAX_PAGE_LIMIT = 10_000

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryRecord)

    @staticmethod
    def _validate_scope_update(values: dict[str, Any]) -> dict[str, Any]:
        validated = dict(values)
        required = {"user_id", "organization_id"}
        fields = (
            "user_id",
            "memory_user_id",
            "agent_id",
            "project_id",
            "organization_id",
            "session_id",
        )
        for field in fields:
            if field not in validated:
                continue
            value = validated[field]
            if value is None:
                if field in required:
                    raise ValueError(f"{field} cannot be null.")
                validated[field] = None
                continue
            if isinstance(value, uuid.UUID):
                continue
            try:
                validated[field] = uuid.UUID(str(value))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"{field} must be a UUID.") from exc
        return validated

    def _apply_scope_filters(
        self,
        statement: Any,
        *,
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> Any:
        for field, value in (
            ("memory_user_id", memory_user_id),
            ("agent_id", agent_id),
            ("project_id", project_id),
            ("session_id", session_id),
        ):
            if value is None:
                continue
            try:
                normalized = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"{field} must be a UUID.") from exc
            statement = statement.where(getattr(self._model, field) == normalized)
        return statement

    @staticmethod
    def _naive_utc(value: datetime) -> datetime:
        """Normalise an aware datetime to the naive UTC form the columns store."""
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def _apply_as_of_filter(
        self,
        statement: Any,
        *,
        as_of: datetime | None = None,
        event_from: datetime | None = None,
        event_to: datetime | None = None,
    ) -> Any:
        """Constrain a statement to what was believed true in a time window.

        ``as_of`` reproduces the bitemporal "what did we believe at T" query that
        `MemoryFactRepository.get_by_fact_key` already implements, so a caller
        asking for historical truth gets it from the index instead of filtering
        candidates out in Python after ranking. Validity is the half-open
        interval ``[valid_from, valid_to)``.

        ``event_from``/``event_to`` bound when the described event happened,
        which is a different question from when the belief was recorded.
        """
        if as_of is not None:
            reference = self._naive_utc(as_of)
            statement = statement.where(self._model.valid_from <= reference)
            statement = statement.where(
                or_(
                    self._model.valid_to.is_(None),
                    self._model.valid_to > reference,
                )
            )
        if event_from is not None:
            column = self._model.event_at
            statement = statement.where(
                or_(column.is_(None), column >= self._naive_utc(event_from))
            )
        if event_to is not None:
            column = self._model.event_at
            statement = statement.where(
                or_(column.is_(None), column < self._naive_utc(event_to))
            )
        return statement

    def _apply_tag_filter(self, statement: Any, tags: Sequence[str]) -> Any:
        """Keep rows whose tags overlap `tags`; an empty filter stays unset.

        `tags && ARRAY[]` is false for every row, so binding an empty (or None)
        list would silently return nothing rather than apply no tag filter.
        """
        if not tags:
            return statement
        return statement.where(self._model.tags.op("&&")(list(tags)))

    @classmethod
    def _bounded_limit(cls, limit: int | None) -> int:
        """Guarantee a bounded read for the limit-taking listing methods."""
        if limit is None:
            return cls._DEFAULT_PAGE_LIMIT
        try:
            bounded = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be a positive integer.") from exc
        if bounded <= 0:
            return 1
        return min(bounded, cls._MAX_PAGE_LIMIT)

    @staticmethod
    def _compatibility_error(message: str) -> Exception:
        from contexta.services.embedding import EmbeddingCompatibilityError

        return EmbeddingCompatibilityError(message)

    @staticmethod
    def _dimension_error(message: str) -> Exception:
        from contexta.services.embedding import EmbeddingDimensionError

        return EmbeddingDimensionError(message)

    @staticmethod
    def _storage_column_for_dimensions(dimensions: int) -> str:
        if dimensions == OFFLINE_EMBEDDING_PROFILE.dimensions:
            return "embedding_1024"
        if dimensions == ONLINE_EMBEDDING_PROFILE.dimensions:
            return "embedding"
        raise MemoryRepository._dimension_error(
            f"Unsupported embedding dimension {dimensions}. Persisted vectors must be 1024 or 1536 "
            "dimensional; vectors are never padded or truncated."
        )

    @classmethod
    def _canonical_profile(
        cls,
        profile: EmbeddingProfile | str | None = None,
        dimensions: int | None = None,
    ) -> EmbeddingProfile:
        if isinstance(profile, EmbeddingProfile):
            profile_name = EMBEDDING_PROFILE_ALIASES.get(
                str(profile.name).strip().casefold(),
                str(profile.name).strip().casefold(),
            )
            if profile_name == OFFLINE_EMBEDDING_PROFILE.name:
                base_profile = OFFLINE_EMBEDDING_PROFILE
            elif profile_name == ONLINE_EMBEDDING_PROFILE.name:
                base_profile = ONLINE_EMBEDDING_PROFILE
            else:
                raise cls._dimension_error(
                    f"Unsupported embedding profile {profile.name!r}; supported persisted profiles are "
                    f"{OFFLINE_EMBEDDING_PROFILE.name!r} and {ONLINE_EMBEDDING_PROFILE.name!r}."
                )
            if profile.provider != base_profile.provider:
                raise cls._dimension_error(
                    f"Embedding profile {profile.name!r} has an incompatible provider."
                )
            resolved = EmbeddingProfile(
                name=base_profile.name,
                dimensions=base_profile.dimensions,
                model=profile.model,
                version=profile.version,
                provider=base_profile.provider,
                storage_column=base_profile.storage_column,
            )
        elif profile:
            profile_name = EMBEDDING_PROFILE_ALIASES.get(
                str(profile).strip().casefold(),
                str(profile).strip().casefold(),
            )
            if profile_name == OFFLINE_EMBEDDING_PROFILE.name:
                resolved = OFFLINE_EMBEDDING_PROFILE
            elif profile_name == ONLINE_EMBEDDING_PROFILE.name:
                resolved = ONLINE_EMBEDDING_PROFILE
            else:
                raise cls._dimension_error(
                    f"Unsupported embedding profile {profile!r}; supported persisted profiles are "
                    f"{OFFLINE_EMBEDDING_PROFILE.name!r} and {ONLINE_EMBEDDING_PROFILE.name!r}."
                )
        else:
            raise cls._dimension_error(
                "An explicit embedding profile is required for vector persistence; dimensions alone "
                "do not identify a provider or vector space."
            )
        if dimensions is not None and resolved.dimensions != dimensions:
            raise cls._dimension_error(
                f"Embedding profile {resolved.name!r} requires {resolved.dimensions} dimensions, "
                f"got {dimensions}; vectors are never padded or truncated."
            )
        expected_column = cls._storage_column_for_dimensions(resolved.dimensions)
        if resolved.storage_column != expected_column:
            raise cls._dimension_error(
                f"Embedding profile {resolved.name!r} must use the {expected_column!r} column."
            )
        return resolved

    @classmethod
    def _profile_from_metadata(
        cls,
        profile: Any,
        model: Any,
        version: Any,
        dimensions: int,
        record_id: uuid.UUID,
    ) -> EmbeddingProfile:
        base_profile = cls._canonical_profile(profile, dimensions)
        model_name = str(model).strip() if model is not None else ""
        profile_version = str(version).strip() if version is not None else ""
        if not model_name or not profile_version:
            raise cls._compatibility_error(
                f"Memory {record_id} has incomplete embedding model or version metadata."
            )
        return EmbeddingProfile(
            name=base_profile.name,
            dimensions=base_profile.dimensions,
            model=model_name,
            version=profile_version,
            provider=base_profile.provider,
            storage_column=base_profile.storage_column,
        )

    @classmethod
    def _validate_unlabelled_dimensions(
        cls,
        metadata: dict[str, Any],
        dimensions: int,
        record_id: uuid.UUID,
    ) -> None:
        provider_keys = ("embedding_profile", "embedding_model", "embedding_version")
        if any(metadata[key] is not None for key in provider_keys):
            raise cls._compatibility_error(
                f"Memory {record_id} has partial embedding provider metadata."
            )
        recorded_dimensions = metadata["embedding_dimensions"]
        if recorded_dimensions is None:
            return
        try:
            recorded_dimensions = int(recorded_dimensions)
        except (TypeError, ValueError) as exc:
            raise cls._compatibility_error(
                f"Memory {record_id} has invalid embedding dimension metadata."
            ) from exc
        if recorded_dimensions != dimensions:
            raise cls._compatibility_error(
                f"Memory {record_id} embedding dimension metadata does not match its vector."
            )

    @classmethod
    def _query_profile(
        cls,
        dimensions: int,
        profile: EmbeddingProfile | str | None,
    ) -> EmbeddingProfile:
        if profile is not None:
            return cls._canonical_profile(profile, dimensions)
        try:
            configured = get_settings().embedding_profile_definition()
        except ValueError as exc:
            raise cls._dimension_error(
                f"Cannot select an embedding profile for a {dimensions}-dimensional query: {exc}"
            ) from exc
        if configured.dimensions != dimensions:
            raise cls._dimension_error(
                f"Query embedding dimension {dimensions} does not match active profile "
                f"{configured.name!r} ({configured.dimensions} dimensions). Set the matching "
                "CONTEXTA_EMBEDDING_PROFILE and CONTEXTA_EMBEDDING_DIMENSIONS, or pass an explicit "
                "profile for a separate vector space."
            )
        return cls._canonical_profile(configured, dimensions)

    @staticmethod
    def _vector_length(value: Any, name: str, record_id: uuid.UUID | None) -> int:
        try:
            dimensions = len(value)
        except TypeError as exc:
            raise MemoryRepository._dimension_error(
                f"Memory {record_id} has an unreadable {name} vector."
            ) from exc
        if dimensions <= 0:
            raise MemoryRepository._dimension_error(
                f"Memory {record_id} has an empty {name} vector."
            )
        return dimensions

    @staticmethod
    def _set_record_value(record: MemoryRecord, name: str, value: Any) -> None:
        try:
            state = sa_inspect(record)
        except NoInspectionAvailable:
            state = None
        committed = bool(
            state is not None
            and (
                getattr(state, "persistent", False)
                or getattr(state, "detached", False)
                or getattr(state, "pending", False)
            )
        )
        if committed:
            set_committed_value(record, name, value)
        else:
            setattr(record, name, value)

    @classmethod
    def _stored_vectors(cls, record: MemoryRecord) -> list[tuple[str, Any, int]]:
        vectors: list[tuple[str, Any, int]] = []
        for name in ("embedding_1024", "embedding"):
            value = getattr(record, name, None)
            if value is None:
                continue
            dimensions = cls._vector_length(value, name, record.id)
            expected_dimensions = 1024 if name == "embedding_1024" else 1536
            if dimensions != expected_dimensions:
                raise cls._dimension_error(
                    f"Memory {record.id} stores a {dimensions}-dimensional vector in {name!r}; "
                    f"that column requires {expected_dimensions} dimensions."
                )
            vectors.append((name, value, dimensions))
        return vectors

    @classmethod
    def _apply_profile_to_record(
        cls,
        record: MemoryRecord,
        embedding: list[float],
        profile: EmbeddingProfile,
    ) -> None:
        if profile.storage_column == "embedding_1024":
            cls._set_record_value(record, "embedding_1024", embedding)
            cls._set_record_value(record, "embedding", None)
        else:
            cls._set_record_value(record, "embedding_1024", None)
            cls._set_record_value(record, "embedding", embedding)
        cls._set_record_value(record, "embedding_profile", profile.name)
        cls._set_record_value(record, "embedding_model", profile.model)
        cls._set_record_value(record, "embedding_version", profile.version)
        cls._set_record_value(record, "embedding_dimensions", profile.dimensions)

    @classmethod
    def _prepare_embedding(cls, record: MemoryRecord) -> None:
        vectors = cls._stored_vectors(record)
        if len(vectors) > 1:
            raise cls._compatibility_error(
                f"Memory {record.id} has vectors in multiple embedding columns: "
                f"{', '.join(name for name, _, _ in vectors)}. Select one profile and run an "
                "explicit reviewed backfill; automatic re-embedding is disabled."
            )
        metadata = {
            "embedding_profile": record.embedding_profile,
            "embedding_model": record.embedding_model,
            "embedding_version": record.embedding_version,
            "embedding_dimensions": record.embedding_dimensions,
        }
        present = [value is not None for value in metadata.values()]
        if not vectors:
            if any(present) and not all(present):
                raise cls._compatibility_error(
                    f"Memory {record.id} has partial embedding metadata without a vector."
                )
            return
        vector_name, _, dimensions = vectors[0]
        if not all(present):
            cls._validate_unlabelled_dimensions(metadata, dimensions, record.id)
            cls._set_record_value(record, "embedding_dimensions", dimensions)
            return
        try:
            metadata_dimensions = int(metadata["embedding_dimensions"])
        except (TypeError, ValueError) as exc:
            raise cls._compatibility_error(
                f"Memory {record.id} has invalid embedding dimension metadata."
            ) from exc
        if metadata_dimensions != dimensions:
            raise cls._compatibility_error(
                f"Memory {record.id} embedding dimension metadata does not match its vector."
            )
        profile = cls._profile_from_metadata(
            metadata["embedding_profile"],
            metadata["embedding_model"],
            metadata["embedding_version"],
            dimensions,
            record.id,
        )
        if vector_name != profile.storage_column:
            raise cls._compatibility_error(
                f"Memory {record.id} stores its vector in {vector_name!r}, which does not match "
                f"profile {profile.name!r}."
            )

    @classmethod
    def _project_active_embeddings(cls, records: Sequence[MemoryRecord]) -> None:
        for record in records:
            vectors = cls._stored_vectors(record)
            if len(vectors) > 1:
                raise cls._compatibility_error(
                    f"Memory {record.id} contains both 1024 and 1536 embedding columns; "
                    "select one profile and run an explicit reviewed backfill."
                )
            if not vectors:
                continue
            vector_name, _, dimensions = vectors[0]
            metadata = {
                "embedding_profile": record.embedding_profile,
                "embedding_model": record.embedding_model,
                "embedding_version": record.embedding_version,
                "embedding_dimensions": record.embedding_dimensions,
            }
            present = [value is not None for value in metadata.values()]
            if not all(present):
                cls._validate_unlabelled_dimensions(metadata, dimensions, record.id)
                continue
            try:
                metadata_dimensions = int(metadata["embedding_dimensions"])
            except (TypeError, ValueError) as exc:
                raise cls._compatibility_error(
                    f"Memory {record.id} has invalid embedding dimension metadata."
                ) from exc
            if metadata_dimensions != dimensions:
                raise cls._compatibility_error(
                    f"Memory {record.id} embedding dimension metadata does not match its vector."
                )
            profile = cls._profile_from_metadata(
                metadata["embedding_profile"],
                metadata["embedding_model"],
                metadata["embedding_version"],
                dimensions,
                record.id,
            )
            if vector_name != profile.storage_column:
                raise cls._compatibility_error(
                    f"Memory {record.id} stores its vector in {vector_name!r}, which does not match "
                    f"profile {profile.name!r}."
                )

    def _hydrate_records(self, records: Sequence[MemoryRecord]) -> list[MemoryRecord]:
        hydrated = [self._decrypt_record(record) for record in records]
        self._project_active_embeddings([record for record in hydrated if record is not None])
        return [record for record in hydrated if record is not None]

    def _decrypt_record(self, record: MemoryRecord | None) -> MemoryRecord | None:
        if record is None:
            return None
        self._validate_tenant_ownership(record)
        plaintext = record.plaintext_content
        self._set_record_value(record, "content", plaintext)
        return record

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        """Create a new memory record with on-the-fly authenticated encryption."""
        self._validate_tenant_ownership(record)
        if record.search_text is None:
            record.search_text = " ".join(
                part
                for part in (
                    record.title or "",
                    record.plaintext_content,
                    " ".join(record.tags or []),
                )
                if part
            )
        self._prepare_embedding(record)
        if record.content and not record.content.startswith("enc:v1:"):
            record.content = encrypt_content(record.content, str(self._tenant_id))
        created = await super().create(record)
        return self._hydrate_records([created])[0]

    async def get_by_id(self, record_id: uuid.UUID) -> MemoryRecord | None:
        """Retrieve a single memory record by ID with on-the-fly decryption."""
        record = await super().get_by_id(record_id)
        hydrated = self._hydrate_records([record]) if record is not None else []
        return hydrated[0] if hydrated else None

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories for a specific user within the tenant."""
        stmt = select(self._model).where(self._model.user_id == user_id)
        stmt = self._apply_scope_filters(
            stmt,
            memory_user_id=memory_user_id,
            agent_id=agent_id,
            project_id=project_id,
            session_id=session_id,
        )
        stmt = stmt.offset(offset).limit(self._bounded_limit(limit))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def get_linked_to_entities(
        self,
        entity_ids: Sequence[uuid.UUID],
        *,
        user_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> Sequence[MemoryRecord]:
        """Retrieve the memories linked to any of `entity_ids`, scoped to the tenant.

        Both sides of the junction are scoped, not just the link row: the link's
        `organization_id` is a denormalized copy the two foreign keys do not
        enforce, so a link stamped with the caller's organization can still
        point at another organization's memory.

        The rows are returned with their stored column values rather than
        hydrated. The graph routes have always published `content` exactly as
        stored, and decrypting here would change those bytes.
        """
        if not entity_ids:
            return []
        stmt = (
            select(self._model)
            .join(MemoryEntityLink, self._model.id == MemoryEntityLink.memory_id)
            .where(MemoryEntityLink.entity_id.in_(entity_ids))
            .distinct()
        )
        if user_id is not None:
            stmt = stmt.where(self._model.user_id == user_id)
        if limit is not None:
            stmt = stmt.limit(self._bounded_limit(limit))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def _l2_normalize(values: list[float]) -> list[float]:
        """Scale the query vector to unit length before handing it to pgvector.

        The Python scorer normalises both sides, so normalising here keeps the
        database ordering and the Python score on the same scale. A zero vector
        is passed through untouched: dividing by its norm is undefined and
        raising would change existing caller behaviour.
        """
        norm = math.sqrt(sum(value * value for value in values))
        if norm <= 0.0:
            return values
        return [value / norm for value in values]

    @classmethod
    def _hnsw_ef_search(cls, limit: int) -> int:
        """Pick the HNSW search breadth for a single vector query.

        Capped at the configured value so a large LIMIT cannot inflate graph
        traversal, and floored at pgvector's own default (40) so recall is never
        worse than the pre-existing behaviour. ef_search may legitimately sit
        below the requested row count: hnsw.iterative_scan keeps traversing the
        graph until enough rows survive the filters.
        """
        configured = int(get_settings().hnsw_ef_search)
        return max(HNSW_EF_SEARCH_FLOOR, min(int(limit), configured))

    async def _apply_hnsw_search_settings(self, limit: int) -> None:
        """Scope the pgvector HNSW GUCs to the current transaction.

        is_local=True keeps the tuning from leaking onto a pooled connection, and
        issuing it only on the vector path costs one extra round trip per vector
        query instead of on every repository call. Both values are bound
        parameters; an unsupported pgvector build simply ignores the unknown GUC
        instead of failing the query.
        """
        await self._session.execute(
            select(
                func.set_config("hnsw.ef_search", str(self._hnsw_ef_search(limit)), True),
                func.set_config("hnsw.iterative_scan", str(get_settings().hnsw_iterative_scan), True),
            )
        )

    async def get_by_vector_similarity(
        self,
        user_id: uuid.UUID | None,
        embedding: list[float],
        *,
        limit: int = 100,
        include_archived: bool = False,
        include_cold: bool = True,
        memory_types: Sequence[MemoryType | str] = (),
        tags: Sequence[str] = (),
        profile: EmbeddingProfile | str | None = None,
        include_legacy: bool = False,
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
    ) -> Sequence[MemoryRecord]:
        """Vector-similarity search, optionally restricted to what was true at `as_of`."""
        """Retrieve candidates from the vector column matching the query profile."""
        dimensions = self._vector_length(embedding, "query_embedding", user_id)
        try:
            values = [float(value) for value in embedding]
        except (TypeError, ValueError) as exc:
            raise self._dimension_error("The query embedding contains non-numeric values.") from exc
        if any(not math.isfinite(value) for value in values):
            raise self._dimension_error("The query embedding contains non-finite values.")
        values = self._l2_normalize(values)
        resolved_profile = self._query_profile(dimensions, profile)
        vector_column_name = resolved_profile.storage_column
        vector_column = getattr(self._model, vector_column_name)
        other_column_name = "embedding" if vector_column_name == "embedding_1024" else "embedding_1024"
        other_column = getattr(self._model, other_column_name)
        exact_metadata = (
            (self._model.embedding_profile == resolved_profile.name)
            & (self._model.embedding_model == resolved_profile.model)
            & (self._model.embedding_version == resolved_profile.version)
            & (self._model.embedding_dimensions == resolved_profile.dimensions)
        )
        if include_legacy:
            metadata_filter = or_(
                exact_metadata,
                and_(
                    self._model.embedding_profile.is_(None),
                    self._model.embedding_model.is_(None),
                    self._model.embedding_version.is_(None),
                    or_(
                        self._model.embedding_dimensions.is_(None),
                        self._model.embedding_dimensions == resolved_profile.dimensions,
                    ),
                ),
            )
        else:
            metadata_filter = exact_metadata
        stmt = (
            select(self._model)
            .where(self._model.valid_to.is_(None))
            .where(vector_column.is_not(None))
            .where(other_column.is_(None))
            .where(metadata_filter)
        )
        if user_id is not None:
            stmt = stmt.where(self._model.user_id == user_id)
        stmt = self._apply_scope_filters(
            stmt,
            memory_user_id=memory_user_id,
            agent_id=agent_id,
            project_id=project_id,
            session_id=session_id,
        )
        if not include_archived:
            stmt = stmt.where(self._model.is_archived.is_(False))
        if not include_cold:
            stmt = stmt.where(self._model.memory_state != MemoryState.COLD.value)
        if memory_types:
            type_values = [
                memory_type.value if hasattr(memory_type, "value") else str(memory_type)
                for memory_type in memory_types
            ]
            stmt = stmt.where(self._model.memory_type.in_(type_values))
        if tags:
            stmt = self._apply_tag_filter(stmt, tags)
        stmt = self._apply_as_of_filter(stmt, as_of=as_of)
        stmt = self._scope_select(stmt)
        stmt = stmt.order_by(vector_column.cosine_distance(values)).limit(limit)
        await self._apply_hnsw_search_settings(limit)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    _LEXICAL_STOPWORDS = frozenset(
        {
            "a", "about", "after", "all", "am", "an", "and", "are", "as",
            "at", "be", "been", "being", "by", "did", "do", "does", "for",
            "from", "had", "has", "have", "how", "i", "in", "into", "is",
            "it", "me", "my", "of", "on", "or", "our", "out", "she", "so",
            "than", "that", "the", "their", "them", "there", "these", "they",
            "this", "to", "was", "we", "were", "what", "when", "where",
            "which", "who", "why", "with", "would", "you", "your",
        }
    )

    @classmethod
    def _lexical_tsquery_text(cls, query_text: str) -> str | None:
        terms: list[str] = []
        for term in re.findall(r"[a-z0-9]+", query_text.casefold()):
            if len(term) < 2 or term in cls._LEXICAL_STOPWORDS:
                continue
            if term not in terms:
                terms.append(term)
        if not terms:
            return None
        return " OR ".join(terms)

    async def get_by_lexical_similarity(
        self,
        user_id: uuid.UUID,
        query_text: str,
        *,
        limit: int = 100,
        include_archived: bool = False,
        include_cold: bool = True,
        memory_types: Sequence[MemoryType | str] = (),
        tags: Sequence[str] = (),
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
    ) -> Sequence[MemoryRecord]:
        """Lexical search, optionally restricted to what was true at `as_of`."""
        search_vector = getattr(self._model, "search_vector", None)
        tsquery_text = self._lexical_tsquery_text(query_text)
        if search_vector is None or tsquery_text is None:
            return []

        # One bound query text feeds both the match predicate and the rank. `@@` is
        # what the GIN index can serve; ranking a scalar function in the WHERE
        # clause would force a full scan and evaluate ts_rank_cd per row.
        ts_query = func.websearch_to_tsquery("english", tsquery_text)
        # Flag 32 is RANK_NORM_RDIVRPLUSONE (rank / (rank + 1)): it normalises the
        # score into (0, 1] and is strictly monotonic, so the ordering below is
        # unchanged.
        rank = func.ts_rank_cd(search_vector, ts_query, 32)
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.valid_to.is_(None))
            .where(search_vector.op("@@")(ts_query))
        )
        stmt = self._apply_scope_filters(
            stmt,
            memory_user_id=memory_user_id,
            agent_id=agent_id,
            project_id=project_id,
            session_id=session_id,
        )
        # rank stays the primary key; created_at/id only break rank ties inside the
        # GIN-matched set, which Postgres sorts with a bounded top-N heapsort.
        stmt = stmt.order_by(rank.desc(), self._model.created_at.desc(), self._model.id.asc()).limit(limit)
        if not include_archived:
            stmt = stmt.where(self._model.is_archived.is_(False))
        if not include_cold:
            stmt = stmt.where(self._model.memory_state != MemoryState.COLD.value)
        if memory_types:
            type_values = [
                memory_type.value if hasattr(memory_type, "value") else str(memory_type)
                for memory_type in memory_types
            ]
            stmt = stmt.where(self._model.memory_type.in_(type_values))
        if tags:
            stmt = self._apply_tag_filter(stmt, tags)
        stmt = self._apply_as_of_filter(stmt, as_of=as_of)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def persist(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        session_id: uuid.UUID | None,
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        memory: ExtractedMemory,
        confidence: float,
        importance: float,
        utility_score: float = 0.0,
        is_pinned: bool = False,
        valid_from: datetime | None = None,
        event_at: datetime | None = None,
        observed_at: datetime | None = None,
        temporal_precision: str | None = None,
        temporal_basis: str | None = None,
        fact_key: str | None = None,
        lineage_id: str | None = None,
        source_id: str | None = None,
        source_message_id: str | None = None,
        graph_edges: Sequence[EntityEdge] = (),
    ) -> MemoryRecord:
        """Persist a fully-scored memory and any graph edges."""
        record = MemoryRecord(
            user_id=user_id,
            organization_id=organization_id,
            memory_user_id=memory_user_id,
            agent_id=agent_id,
            project_id=project_id,
            session_id=session_id,
            memory_type=memory.memory_type.value if hasattr(memory.memory_type, "value") else str(memory.memory_type),

            title=memory.title,
            content=memory.content,
            structured_data=memory.structured_data,
            source_type=memory.source_type.value if hasattr(memory.source_type, "value") else str(memory.source_type),
            confidence=confidence,
            importance=importance,
            utility_score=utility_score,
            tags=memory.tags,
            memory_state=MemoryState.ACTIVE.value,
            is_pinned=is_pinned,
            is_archived=False,
            valid_from=valid_from or datetime.utcnow(),
            valid_to=None,
            event_at=event_at,
            observed_at=observed_at,
            temporal_precision=temporal_precision,
            temporal_basis=temporal_basis,
            fact_key=fact_key,
            lineage_id=lineage_id,
            source_id=source_id,
            source_message_id=source_message_id,
            embedding=getattr(memory, "embedding", None),
        )
        persisted = await self.create(record)

        for edge in graph_edges:
            self._validate_tenant_ownership(edge)
            self._session.add(edge)

        if graph_edges:
            await self._session.flush()

        return persisted

    async def get_by_type(
        self,
        user_id: uuid.UUID,
        memory_type: MemoryType | str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve current, unarchived memories of a specific type for a user.

        Superseded and archived rows are excluded: callers of this method fold a
        new extraction into the row they matched, and a row that is already out
        of the current set would absorb the new evidence where no read will ever
        see it again.
        """
        type_val = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.memory_type == type_val)
            .where(self._model.valid_to.is_(None))
            .where(self._model.is_archived.is_(False))
            .order_by(self._model.created_at.desc(), self._model.id.asc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def get_current_by_fact_key(
        self,
        fact_key: str,
        *,
        user_id: uuid.UUID | None = None,
        memory_type: MemoryType | str | None = None,
        limit: int = 50,
    ) -> Sequence[MemoryRecord]:
        """Retrieve the current rows occupying one fact slot.

        This is the fact-key slot read that supersession needs, and it is the
        only shape `ix_memory_record_fact_key_current` can serve: the index leads
        with (organization_id, user_id, fact_key) and is partial on
        `valid_to IS NULL`, so both the tenant and the user must be bound and the
        predicate must be the current-row one. Ordering is newest-first so the
        caller sees the most recently asserted version of the slot first.
        """
        normalized_key = str(fact_key).strip()
        if not normalized_key:
            return []
        stmt = (
            select(self._model)
            .where(self._model.fact_key == normalized_key)
            .where(self._model.valid_to.is_(None))
        )
        if user_id is not None:
            stmt = stmt.where(self._model.user_id == user_id)
        if memory_type is not None:
            type_val = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
            stmt = stmt.where(self._model.memory_type == type_val)
        stmt = (
            self._scope_select(stmt)
            .order_by(self._model.valid_from.desc(), self._model.id.desc())
            .limit(self._bounded_limit(limit))
        )
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def get_by_state(
        self,
        user_id: uuid.UUID,
        state: MemoryState | str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories in a specific lifecycle state."""
        state_val = state.value if hasattr(state, "value") else str(state)
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.memory_state == state_val)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def get_by_session(
        self,
        session_id: uuid.UUID,
    ) -> Sequence[MemoryRecord]:
        """Retrieve all memories extracted from a specific session."""
        stmt = select(self._model).where(self._model.session_id == session_id)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def get_current_truths(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
    ) -> Sequence[MemoryRecord]:
        """Retrieve current (non-superseded) memories for a user."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.valid_to.is_(None))
        )
        stmt = self._apply_scope_filters(
            stmt,
            memory_user_id=memory_user_id,
            agent_id=agent_id,
            project_id=project_id,
            session_id=session_id,
        )
        stmt = stmt.offset(offset).limit(self._bounded_limit(limit))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def get_unpinned_by_state(
        self,
        state: MemoryState | str,
        *,
        limit: int = 500,
    ) -> Sequence[MemoryRecord]:
        """Retrieve unpinned memories in a given state (for decay engine)."""
        state_val = state.value if hasattr(state, "value") else str(state)
        stmt = (
            select(self._model)
            .where(self._model.memory_state == state_val)
            .where(self._model.is_pinned == False)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def _guard_identity_update(
        self,
        record_id: uuid.UUID,
        values: dict[str, Any],
    ) -> None:
        """Refuse writes that would rewrite a memory's identity or its validity.

        Ported from `MemoryFactRepository.update_by_id`, which guards the same
        three columns on `memory_fact`:

        * `fact_key` names the fact slot, so re-pointing a row at another slot
          strands it in a slot it no longer belongs to and leaves its old slot
          with no current truth;
        * a validity window may not be inverted;
        * a row that is already closed may not be closed again, which is what
          let a repeated or concurrent supersession write a second
          `MemoryVersion` for history that was already recorded.

        Only those columns are inspected, and only then is the row read, so the
        hot updates (touch_accessed, pinning, embeddings) keep their single
        statement.
        """
        if not _IDENTITY_COLUMNS.intersection(values):
            return
        existing = await super().get_by_id(record_id)
        if existing is None:
            return
        if "fact_key" in values and values["fact_key"] != existing.fact_key:
            raise MemoryFactKeyMutationError("MemoryRecord.fact_key is immutable")
        if values.get("valid_to") is None:
            return
        valid_to = self._naive_utc(values["valid_to"])
        if existing.valid_to is not None:
            raise ValueError("Only a current memory can be superseded.")
        valid_from = values.get("valid_from") or existing.valid_from
        if valid_to < self._naive_utc(valid_from):
            raise ValueError("The memory validity range is inverted.")
        values["valid_to"] = valid_to

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        update_values = self._validate_scope_update(values)
        await self._guard_identity_update(record_id, update_values)
        embedding_keys = [key for key in ("embedding", "embedding_1024") if key in update_values]
        metadata_keys = {
            "embedding_profile",
            "embedding_model",
            "embedding_version",
            "embedding_dimensions",
        }
        if len(embedding_keys) > 1:
            raise self._compatibility_error(
                f"Memory {record_id} cannot receive vectors in both embedding columns; "
                "select one embedding profile and run an explicit reviewed backfill."
            )
        rows = 0
        if embedding_keys:
            embedding = update_values.pop(embedding_keys[0])
            dimensions = self._vector_length(embedding, embedding_keys[0], record_id)
            supplied_metadata = {
                key for key in metadata_keys if key in update_values
            }
            if supplied_metadata and supplied_metadata != metadata_keys:
                raise self._compatibility_error(
                    f"Memory {record_id} received partial embedding metadata; provide profile, model, "
                    "version, and dimensions together."
                )
            source_column = embedding_keys[0]
            expected_source_column = self._storage_column_for_dimensions(dimensions)
            if source_column != expected_source_column:
                raise self._dimension_error(
                    f"Memory {record_id} received a {dimensions}-dimensional vector in "
                    f"{source_column!r}; it belongs in {expected_source_column!r}."
                )
            profile_value = update_values.get("embedding_profile")
            profile: EmbeddingProfile | None = None
            if supplied_metadata:
                if any(update_values.get(key) is None for key in metadata_keys):
                    raise self._compatibility_error(
                        f"Memory {record_id} received null embedding metadata; provide profile, model, "
                        "version, and dimensions."
                    )
                metadata_dimensions = update_values.get("embedding_dimensions")
                try:
                    metadata_dimensions = int(metadata_dimensions)
                except (TypeError, ValueError) as exc:
                    raise self._dimension_error(
                        f"Memory {record_id} received invalid embedding dimension metadata."
                    ) from exc
                if metadata_dimensions != dimensions:
                    raise self._dimension_error(
                        f"Memory {record_id} embedding metadata dimension {metadata_dimensions} "
                        f"does not match vector dimension {dimensions}."
                    )
                profile = self._profile_from_metadata(
                    profile_value,
                    update_values["embedding_model"],
                    update_values["embedding_version"],
                    dimensions,
                    record_id,
                )
            rows = await self.store_embedding(record_id, embedding, profile)
            for key in metadata_keys:
                update_values.pop(key, None)
        elif metadata_keys.intersection(update_values):
            raise self._compatibility_error(
                f"Memory {record_id} has embedding metadata without a vector. Store the vector and "
                "metadata together or use an explicit migration."
            )
        if "content" in update_values:
            content = update_values["content"]
            if isinstance(content, str) and not content.startswith("enc:v1:"):
                existing = await super().get_by_id(record_id)
                if existing is not None:
                    self._validate_tenant_ownership(existing)
                    existing_content = existing.plaintext_content
                    update_values["content"] = encrypt_content(content, str(self._tenant_id))
                    if "search_text" not in update_values:
                        update_values["search_text"] = " ".join(
                            part
                            for part in (
                                str(existing.title or ""),
                                existing_content,
                                " ".join(existing.tags or []),
                            )
                            if part
                        )
                else:
                    update_values["content"] = encrypt_content(content, str(self._tenant_id))
        if not update_values:
            return rows
        content_rows = await super().update_by_id(record_id, update_values)
        return content_rows if content_rows else rows

    async def store_embedding(
        self,
        record_id: uuid.UUID,
        embedding: list[float],
        profile: EmbeddingProfile | str | None = None,
    ) -> int:
        dimensions = self._vector_length(embedding, "embedding", record_id)
        try:
            values = [float(value) for value in embedding]
        except (TypeError, ValueError) as exc:
            raise self._dimension_error(f"Memory {record_id} received a non-numeric vector.") from exc
        if any(not math.isfinite(value) for value in values):
            raise self._dimension_error(f"Memory {record_id} received a non-finite vector.")
        resolved_profile = (
            self._canonical_profile(profile, dimensions) if profile is not None else None
        )
        target_name = (
            resolved_profile.storage_column
            if resolved_profile is not None
            else self._storage_column_for_dimensions(dimensions)
        )
        other_column_name = "embedding" if target_name == "embedding_1024" else "embedding_1024"
        record = await super().get_by_id(record_id)
        if record is None:
            return 0
        self._validate_tenant_ownership(record)
        stored_vectors = self._stored_vectors(record)
        if len(stored_vectors) > 1:
            raise self._compatibility_error(
                f"Memory {record_id} contains vectors in multiple embedding columns; refusing to "
                "mix 1024 and 1536 vectors."
            )
        metadata = {
            "embedding_profile": record.embedding_profile,
            "embedding_model": record.embedding_model,
            "embedding_version": record.embedding_version,
            "embedding_dimensions": record.embedding_dimensions,
        }
        present = [value is not None for value in metadata.values()]
        if any(present) and not all(present):
            self._validate_unlabelled_dimensions(metadata, dimensions, record_id)
        if stored_vectors:
            stored_name, _, stored_dimensions = stored_vectors[0]
            if stored_name != target_name:
                raise self._compatibility_error(
                    f"Memory {record_id} already contains a vector in {stored_name}; refusing to mix it "
                    f"with {target_name}. Select the matching profile and run an explicit reviewed backfill."
                )
            if not all(present):
                self._validate_unlabelled_dimensions(metadata, stored_dimensions, record_id)
            else:
                if resolved_profile is None:
                    raise self._compatibility_error(
                        f"Memory {record_id} has a labeled vector; an explicit matching profile is required "
                        "to replace it."
                    )
                stored_profile = self._profile_from_metadata(
                    metadata["embedding_profile"],
                    metadata["embedding_model"],
                    metadata["embedding_version"],
                    stored_dimensions,
                    record_id,
                )
                if (
                    stored_profile.name != resolved_profile.name
                    or stored_profile.model != resolved_profile.model
                    or stored_profile.version != resolved_profile.version
                    or stored_dimensions != resolved_profile.dimensions
                ):
                    raise self._compatibility_error(
                        f"Memory {record_id} uses embedding profile {stored_profile.name!r}, "
                        f"model {stored_profile.model!r}, version {stored_profile.version!r}, "
                        f"and {stored_dimensions} dimensions; refusing to overwrite it with "
                        f"{resolved_profile.name!r}/{resolved_profile.model!r}/{resolved_profile.version!r}."
                    )
        elif all(present):
            if resolved_profile is None:
                raise self._compatibility_error(
                    f"Memory {record_id} has embedding metadata; an explicit matching profile is required "
                    "to replace its vector."
                )
            try:
                stored_dimensions = int(metadata["embedding_dimensions"])
            except (TypeError, ValueError) as exc:
                raise self._compatibility_error(
                    f"Memory {record_id} has invalid embedding dimension metadata."
                ) from exc
            stored_profile = self._profile_from_metadata(
                metadata["embedding_profile"],
                metadata["embedding_model"],
                metadata["embedding_version"],
                stored_dimensions,
                record_id,
            )
            if (
                stored_profile.name != resolved_profile.name
                or stored_profile.model != resolved_profile.model
                or stored_profile.version != resolved_profile.version
                or stored_dimensions != resolved_profile.dimensions
            ):
                raise self._compatibility_error(
                    f"Memory {record_id} uses embedding profile {stored_profile.name!r}, "
                    f"model {stored_profile.model!r}, version {stored_profile.version!r}, "
                    f"and {stored_dimensions} dimensions; refusing to overwrite it with "
                    f"{resolved_profile.name!r}/{resolved_profile.model!r}/{resolved_profile.version!r}."
                )
        update_values = {target_name: values, "embedding_dimensions": dimensions}
        if resolved_profile is not None:
            update_values.update(
                {
                    "embedding_profile": resolved_profile.name,
                    "embedding_model": resolved_profile.model,
                    "embedding_version": resolved_profile.version,
                }
            )
        rows = await super().update_by_id(record_id, update_values)
        if rows:
            if resolved_profile is not None:
                self._apply_profile_to_record(record, values, resolved_profile)
            else:
                self._set_record_value(record, target_name, values)
                self._set_record_value(record, other_column_name, None)
                for metadata_key in ("embedding_profile", "embedding_model", "embedding_version"):
                    self._set_record_value(record, metadata_key, None)
                self._set_record_value(record, "embedding_dimensions", dimensions)
        return rows

    async def update_state(
        self,
        record_id: uuid.UUID,
        new_state: MemoryState | str,
    ) -> int:
        """Transition a memory to a new lifecycle state."""
        state_val = new_state.value if hasattr(new_state, "value") else str(new_state)
        return await self.update_by_id(record_id, {"memory_state": state_val})

    async def touch_accessed(
        self,
        record_id: uuid.UUID,
        accessed_at: datetime,
    ) -> int:
        """Update the last_accessed_at timestamp for a memory."""
        return await self.update_by_id(
            record_id, {"last_accessed_at": accessed_at}
        )

    async def touch_accessed_many(
        self,
        record_ids: Sequence[uuid.UUID],
        accessed_at: datetime,
    ) -> int:
        if not record_ids:
            return 0
        stmt = (
            update(self._model)
            .where(self._model.id.in_(record_ids))
            .values(last_accessed_at=accessed_at)
        )
        stmt = self._scope_update(stmt)
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def _validate_supersession(
        self,
        record_id: uuid.UUID,
        existing: MemoryRecord,
        valid_to: datetime,
        superseded_by_id: uuid.UUID | None,
    ) -> datetime:
        """Reject the supersessions that would corrupt the validity history.

        Same discipline as `MemoryFactRepository.supersede`: no self
        supersession, no second close, no inverted window, and a replacement
        that is either outside the tenant or sitting in a different fact slot
        cannot stand in for this one.
        """
        if superseded_by_id is not None and superseded_by_id == record_id:
            raise ValueError("A memory cannot supersede itself.")
        if existing.valid_to is not None:
            raise ValueError("Only a current memory can be superseded.")
        end = self._naive_utc(valid_to)
        if end < self._naive_utc(existing.valid_from):
            raise ValueError("The memory validity range is inverted.")
        if superseded_by_id is not None:
            replacement = await super().get_by_id(superseded_by_id)
            if replacement is None:
                raise AuthorizationError("The replacement memory is outside the tenant.")
            if replacement.fact_key != existing.fact_key:
                raise ValueError("A replacement must retain the fact key.")
        return end

    async def _close_validity(self, record_id: uuid.UUID, valid_to: datetime) -> int:
        """Set `valid_to` only while the row is still current.

        The `valid_to IS NULL` predicate is re-checked inside the write, so the
        row count reports whether this caller won the race: exactly one of any
        number of concurrent supersessions gets 1, the rest get 0 and leave the
        row (and its `MemoryVersion`) to the winner.
        """
        stmt = (
            update(self._model)
            .where(self._model.id == record_id)
            .where(self._model.valid_to.is_(None))
            .where(self._model.valid_from <= valid_to)
            .values(valid_to=valid_to)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(self._scope_update(stmt))
        return result.rowcount or 0

    async def supersede_if_current(
        self,
        old_id: uuid.UUID,
        valid_to: datetime,
        *,
        superseded_by_id: uuid.UUID | None = None,
    ) -> int:
        """Close a memory's validity window if it is still current.

        Returns 0 when the record is missing or another writer closed it first,
        which is what makes a repeated or concurrent supersession a no-op
        instead of a second version of the same history. An inverted window is
        still an error, because that is a bug and not a race.
        """
        existing = await super().get_by_id(old_id)
        if existing is None or existing.valid_to is not None:
            return 0
        end = await self._validate_supersession(old_id, existing, valid_to, superseded_by_id)
        return await self._close_validity(old_id, end)

    async def supersede(
        self,
        old_id: uuid.UUID,
        valid_to: datetime,
        *,
        superseded_by_id: uuid.UUID | None = None,
    ) -> int:
        """Mark a memory as superseded by setting its valid_to timestamp.

        Kept for callers that treat a superseded record as a programming error;
        `supersede_if_current` is the variant supersession itself uses.
        """
        existing = await super().get_by_id(old_id)
        if existing is None:
            return 0
        end = await self._validate_supersession(old_id, existing, valid_to, superseded_by_id)
        rows = await self._close_validity(old_id, end)
        if rows == 0:
            raise ValueError("Only a current memory can be superseded.")
        return rows

    async def get_many_by_ids(
        self,
        record_ids: Sequence[uuid.UUID],
    ) -> Sequence[MemoryRecord]:
        """Concurrently retrieve multiple memory records by ID in a single query."""
        if not record_ids:
            return []
        stmt = select(self._model).where(self._model.id.in_(record_ids))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return self._hydrate_records(result.scalars().all())

    async def apply_feedback(
        self,
        record_id: uuid.UUID,
        signal: str,
        user_correction: str | None = None,
        penalty: float = 0.5,
    ) -> MemoryRecord | None:
        """Adjust memory utility score and confidence based on explicit user/agent feedback."""
        memory = await self.get_by_id(record_id)
        if memory is None:
            return None

        now = datetime.utcnow()
        if signal.lower() in {"positive", "up", "thumbs_up"}:
            new_utility = min(1.0, (memory.utility_score or 0.0) + 0.25)
            new_conf = min(1.0, (memory.confidence or 0.5) + 0.1)
            updates: dict[str, Any] = {
                "utility_score": new_utility,
                "confidence": new_conf,
                "last_accessed_at": now,
            }
        else:
            new_utility = max(-1.0, (memory.utility_score or 0.0) - penalty)
            new_conf = max(0.1, (memory.confidence or 0.5) - 0.2)
            updates = {
                "utility_score": new_utility,
                "confidence": new_conf,
                "last_accessed_at": now,
            }
            if user_correction or penalty >= 1.0 or new_utility <= -0.8:
                updates["memory_state"] = MemoryState.ARCHIVED.value
                # A record that is already superseded is out of the current set, so
                # closing it again would fail the guard and change nothing. The
                # closing timestamp is deliberately not assigned to `memory` before
                # the write: update_by_id re-reads the same identity-mapped instance,
                # so an unflushed assignment here reads back as already superseded.
                if memory.valid_to is None:
                    updates["valid_to"] = now

        await self.update_by_id(record_id, updates)
        for field in ("utility_score", "confidence", "memory_state", "valid_to", "last_accessed_at"):
            if field in updates:
                setattr(memory, field, updates[field])
        return memory

    async def purge_all_for_org(self) -> dict[str, int]:
        """Cryptographically shreds and permanently purges all memories, graph nodes, and edges for this tenant."""
        # 1. Delete entity links
        sub_mem = select(MemoryRecord.id).where(MemoryRecord.organization_id == self._tenant_id)
        stmt_links = delete(MemoryEntityLink).where(MemoryEntityLink.memory_id.in_(sub_mem))
        res_links = await self._session.execute(stmt_links)

        # 2. Delete entity edges
        sub_ent = select(Entity.id).where(Entity.organization_id == self._tenant_id)
        stmt_edges = delete(EntityEdge).where(
            (EntityEdge.source_entity_id.in_(sub_ent)) | (EntityEdge.target_entity_id.in_(sub_ent))
        )
        res_edges = await self._session.execute(stmt_edges)

        # 3. Delete entities
        stmt_entities = delete(Entity).where(Entity.organization_id == self._tenant_id)
        res_entities = await self._session.execute(stmt_entities)

        # 4. Delete memories
        stmt_memories = delete(MemoryRecord).where(MemoryRecord.organization_id == self._tenant_id)
        res_memories = await self._session.execute(stmt_memories)

        await self._session.commit()

        return {
            "links_deleted": res_links.rowcount or 0,
            "edges_deleted": res_edges.rowcount or 0,
            "entities_deleted": res_entities.rowcount or 0,
            "memories_deleted": res_memories.rowcount or 0,
        }
