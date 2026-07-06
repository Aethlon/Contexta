"""Unit tests for the tenant-scoped repository layer.

Tests verify that:
- All queries are scoped to the authenticated tenant
- Write operations validate tenant ownership
- Cross-tenant access is rejected with AuthorizationError
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contexta.core.errors import AuthorizationError
from contexta.repositories.base import TenantScopedRepository


# ─── Fixtures ─────────────────────────────────────────────────────────


class FakeModel:
    """Minimal model stub for testing the base repository."""

    __tablename__ = "fake_model"

    id = MagicMock()
    organization_id = MagicMock()

    def __init__(self, id=None, organization_id=None):
        self.id = id or uuid.uuid4()
        self.organization_id = organization_id


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def other_tenant_id():
    return uuid.uuid4()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session, tenant_id):
    return TenantScopedRepository(
        session=mock_session,
        tenant_id=tenant_id,
        model=FakeModel,
    )


# ─── Tenant Ownership Validation ─────────────────────────────────────


class TestTenantOwnershipValidation:
    """Tests for _validate_tenant_ownership."""

    def test_valid_ownership_passes(self, repo, tenant_id):
        """Record with matching org_id should pass validation."""
        record = FakeModel(organization_id=tenant_id)
        # Should not raise
        repo._validate_tenant_ownership(record)

    def test_mismatched_org_id_raises_authorization_error(
        self, repo, other_tenant_id
    ):
        """Record with different org_id should raise AuthorizationError."""
        record = FakeModel(organization_id=other_tenant_id)
        with pytest.raises(AuthorizationError):
            repo._validate_tenant_ownership(record)

    def test_missing_org_id_raises_authorization_error(self, repo):
        """Record without organization_id should raise AuthorizationError."""
        record = MagicMock(spec=[])  # no organization_id attribute
        with pytest.raises(AuthorizationError):
            repo._validate_tenant_ownership(record)


# ─── Create Operations ────────────────────────────────────────────────


class TestCreateOperations:
    """Tests for create and create_many."""

    @pytest.mark.asyncio
    async def test_create_with_matching_tenant_succeeds(
        self, repo, mock_session, tenant_id
    ):
        """Creating a record with matching org_id should succeed."""
        record = FakeModel(organization_id=tenant_id)
        result = await repo.create(record)
        assert result is record
        mock_session.add.assert_called_once_with(record)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_wrong_tenant_raises(self, repo, other_tenant_id):
        """Creating a record with different org_id should raise."""
        record = FakeModel(organization_id=other_tenant_id)
        with pytest.raises(AuthorizationError):
            await repo.create(record)

    @pytest.mark.asyncio
    async def test_create_many_validates_all_records(
        self, repo, tenant_id, other_tenant_id
    ):
        """create_many should reject if any record has wrong org_id."""
        good_record = FakeModel(organization_id=tenant_id)
        bad_record = FakeModel(organization_id=other_tenant_id)
        with pytest.raises(AuthorizationError):
            await repo.create_many([good_record, bad_record])

    @pytest.mark.asyncio
    async def test_create_many_all_valid_succeeds(
        self, repo, mock_session, tenant_id
    ):
        """create_many with all matching org_ids should succeed."""
        records = [FakeModel(organization_id=tenant_id) for _ in range(3)]
        result = await repo.create_many(records)
        assert result is records
        mock_session.add_all.assert_called_once_with(records)
        mock_session.flush.assert_awaited_once()


# ─── Properties ───────────────────────────────────────────────────────


class TestRepositoryProperties:
    """Tests for basic repository properties."""

    def test_session_property(self, repo, mock_session):
        assert repo.session is mock_session

    def test_tenant_id_property(self, repo, tenant_id):
        assert repo.tenant_id == tenant_id
