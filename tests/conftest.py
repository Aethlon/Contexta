"""Pytest configuration and global fixtures."""

import pytest
from unittest.mock import AsyncMock, patch
import uuid

from contexta.api.app import app
from contexta.db import get_db_session
from contexta.models.api_key import ApiKeyRecord
from contexta.repositories.api_key_repo import ApiKeyRepository, CreatedApiKey

# In-memory registry for testing API keys without database connection
_test_api_keys: list[ApiKeyRecord] = []


@pytest.fixture(autouse=True)
def mock_api_key_repository():
    """Patches ApiKeyRepository methods to use a simple in-memory store under test."""
    _test_api_keys.clear()

    async def mock_create_key(self, name, actor_id, scopes):
        import secrets
        from datetime import datetime, timezone
        token = f"mk_live_{secrets.token_urlsafe(32)}"
        record = ApiKeyRecord(
            id=uuid.uuid4(),
            name=name,
            prefix=token[:16],
            token_hash=ApiKeyRepository.hash_token(token),
            organization_id=self.tenant_id,
            actor_id=actor_id,
            scopes=scopes,
            created_at=datetime.now(timezone.utc),
        )
        _test_api_keys.append(record)
        return CreatedApiKey(token=token, record=record)

    async def mock_list_by_org(self):
        return [r for r in _test_api_keys if r.organization_id == self.tenant_id]

    @classmethod
    async def mock_find_by_token(cls, session, raw_token):
        token_hash = ApiKeyRepository.hash_token(raw_token)
        for r in _test_api_keys:
            if r.token_hash == token_hash:
                return r
        return None

    with patch.object(ApiKeyRepository, "create_key", mock_create_key), \
         patch.object(ApiKeyRepository, "list_by_org", mock_list_by_org), \
         patch.object(ApiKeyRepository, "find_by_token", mock_find_by_token):
        yield


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Overrides the FastAPI database session dependency with a mock session."""
    mock_session = AsyncMock()

    # Configure default results for execute queries to prevent common test crashes
    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    async def _get_db_session_override():
        yield mock_session

    app.dependency_overrides[get_db_session] = _get_db_session_override
    yield mock_session
    app.dependency_overrides.clear()
