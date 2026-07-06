"""Base repository with tenant isolation enforcement.

All database access MUST go through TenantScopedRepository to ensure
organization_id filtering is applied to every query. This implements
shared-table multi-tenancy at the data access layer.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import Select, Update, Delete, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.errors import AuthorizationError

T = TypeVar("T")


class TenantScopedRepository(Generic[T]):
    """Base repository that enforces tenant isolation on all operations.

    Every query executed through this repository is automatically scoped
    to the tenant identified by `tenant_id`. Write operations validate
    that the target record's organization_id matches the authenticated
    tenant before proceeding.

    Parameters
    ----------
    session : AsyncSession
        The SQLAlchemy async session for database operations.
    tenant_id : uuid.UUID
        The authenticated organization_id for tenant scoping.
    model : type[T]
        The SQLAlchemy model class this repository manages.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        model: type[T],
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._model = model

    @property
    def session(self) -> AsyncSession:
        """Return the underlying async session."""
        return self._session

    @property
    def tenant_id(self) -> uuid.UUID:
        """Return the authenticated tenant ID."""
        return self._tenant_id

    # ─── Query Interceptors ───────────────────────────────────────────

    def _scope_select(self, stmt: Select[tuple[T]]) -> Select[tuple[T]]:
        """Add tenant isolation WHERE clause to a SELECT statement.

        Automatically appends `WHERE organization_id = :tenant_id` to
        ensure only records belonging to the authenticated tenant are
        returned.
        """
        return stmt.where(self._model.organization_id == self._tenant_id)

    def _scope_update(self, stmt: Update) -> Update:
        """Add tenant isolation WHERE clause to an UPDATE statement.

        Ensures UPDATE operations only affect records belonging to the
        authenticated tenant.
        """
        return stmt.where(self._model.organization_id == self._tenant_id)

    def _scope_delete(self, stmt: Delete) -> Delete:
        """Add tenant isolation WHERE clause to a DELETE statement.

        Ensures DELETE operations only affect records belonging to the
        authenticated tenant.
        """
        return stmt.where(self._model.organization_id == self._tenant_id)

    def _validate_tenant_ownership(self, record: Any) -> None:
        """Validate that a record belongs to the authenticated tenant.

        Raises AuthorizationError if the record's organization_id does
        not match the authenticated tenant_id.

        Parameters
        ----------
        record : Any
            A model instance with an organization_id attribute.

        Raises
        ------
        AuthorizationError
            If the record belongs to a different tenant.
        """
        record_org_id = getattr(record, "organization_id", None)
        if record_org_id is None:
            raise AuthorizationError(
                "Record is missing organization_id — cannot verify tenant ownership."
            )
        if record_org_id != self._tenant_id:
            raise AuthorizationError(
                "Access denied: record belongs to a different organization."
            )

    # ─── CRUD Operations ──────────────────────────────────────────────

    async def get_by_id(self, record_id: uuid.UUID) -> T | None:
        """Retrieve a single record by ID, scoped to the tenant.

        Parameters
        ----------
        record_id : uuid.UUID
            The primary key of the record.

        Returns
        -------
        T | None
            The record if found and belongs to the tenant, else None.
        """
        stmt = select(self._model).where(self._model.id == record_id)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[T]:
        """Retrieve all records for the tenant with pagination.

        Parameters
        ----------
        offset : int
            Number of records to skip.
        limit : int
            Maximum number of records to return.

        Returns
        -------
        Sequence[T]
            List of records belonging to the tenant.
        """
        stmt = select(self._model).offset(offset).limit(limit)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(self, record: T) -> T:
        """Create a new record, validating tenant ownership.

        The record's organization_id must match the authenticated
        tenant_id. If it doesn't, an AuthorizationError is raised.

        Parameters
        ----------
        record : T
            The model instance to persist.

        Returns
        -------
        T
            The persisted record.

        Raises
        ------
        AuthorizationError
            If the record's organization_id doesn't match the tenant.
        """
        self._validate_tenant_ownership(record)
        self._session.add(record)
        await self._session.flush()
        return record

    async def create_many(self, records: Sequence[T]) -> Sequence[T]:
        """Create multiple records, validating tenant ownership for each.

        Parameters
        ----------
        records : Sequence[T]
            The model instances to persist.

        Returns
        -------
        Sequence[T]
            The persisted records.

        Raises
        ------
        AuthorizationError
            If any record's organization_id doesn't match the tenant.
        """
        for record in records:
            self._validate_tenant_ownership(record)
        self._session.add_all(records)
        await self._session.flush()
        return records

    async def update_by_id(
        self,
        record_id: uuid.UUID,
        values: dict[str, Any],
    ) -> int:
        """Update a record by ID, scoped to the tenant.

        Parameters
        ----------
        record_id : uuid.UUID
            The primary key of the record to update.
        values : dict[str, Any]
            Column-value pairs to update.

        Returns
        -------
        int
            Number of rows affected (0 or 1).
        """
        stmt = (
            update(self._model)
            .where(self._model.id == record_id)
            .values(**values)
        )
        stmt = self._scope_update(stmt)
        result = await self._session.execute(stmt)
        return result.rowcount

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        """Delete a record by ID, scoped to the tenant.

        Parameters
        ----------
        record_id : uuid.UUID
            The primary key of the record to delete.

        Returns
        -------
        int
            Number of rows affected (0 or 1).
        """
        stmt = delete(self._model).where(self._model.id == record_id)
        stmt = self._scope_delete(stmt)
        result = await self._session.execute(stmt)
        return result.rowcount

    async def exists(self, record_id: uuid.UUID) -> bool:
        """Check if a record exists for the tenant.

        Parameters
        ----------
        record_id : uuid.UUID
            The primary key to check.

        Returns
        -------
        bool
            True if the record exists and belongs to the tenant.
        """
        record = await self.get_by_id(record_id)
        return record is not None
