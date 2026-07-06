"""Property-based tests for observation payload validation.

**Validates: Requirements 1.3, 1.4, 1.5**

Uses Hypothesis to verify:
- Property 1: Observation payload validation boundary (size-based acceptance/rejection)
- Property 2: Observation payload field validation (missing required fields produce errors)
"""

import json
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app
from contexta.config.settings import get_settings

MAX_PAYLOAD_SIZE = get_settings().max_observation_size_bytes  # 1_048_576 bytes (1MB)

REQUIRED_FIELDS = ["user_id", "organization_id", "session_id", "messages"]


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_valid_payload() -> dict:
    """Create a minimal valid observation payload dict."""
    return {
        "user_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "session_id": str(uuid4()),
        "messages": [{"role": "user", "content": "Hello"}],
    }


def _make_payload_of_size(target_size: int) -> bytes:
    """Create a valid JSON payload that is approximately target_size bytes.

    Returns the raw bytes of the JSON-encoded payload.
    """
    base = {
        "user_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "session_id": str(uuid4()),
        "messages": [{"role": "user", "content": ""}],
    }
    base_bytes = json.dumps(base).encode("utf-8")
    base_size = len(base_bytes)

    if target_size <= base_size:
        # Can't make it smaller than the base structure; just return base
        return base_bytes

    # Fill the content field to reach target_size
    # The content field adds quotes and escaping overhead, but 'a' chars are safe
    padding_needed = target_size - base_size
    base["messages"][0]["content"] = "a" * padding_needed
    result = json.dumps(base).encode("utf-8")

    # Fine-tune: if we overshot, trim; if we undershot, pad
    while len(result) > target_size:
        padding_needed -= 1
        base["messages"][0]["content"] = "a" * padding_needed
        result = json.dumps(base).encode("utf-8")

    return result


# ---------------------------------------------------------------------------
# Property 1: Observation payload validation boundary
#
# For any observation payload, if its serialized size exceeds 1MB the system
# SHALL reject it with a size error, and if its size is within 1MB and all
# required fields are present the system SHALL accept it.
# ---------------------------------------------------------------------------


class TestProperty1PayloadSizeBoundary:
    """Property 1: Observation payload validation boundary.

    **Validates: Requirements 1.3**
    """

    @given(
        excess=st.integers(min_value=1, max_value=512 * 1024),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_payloads_exceeding_1mb_are_rejected(
        self, client: AsyncClient, excess: int
    ) -> None:
        """Payloads larger than 1MB must be rejected with 422 and a size error."""
        target_size = MAX_PAYLOAD_SIZE + excess
        payload_bytes = _make_payload_of_size(target_size)

        # Ensure we actually exceed the limit
        assume(len(payload_bytes) > MAX_PAYLOAD_SIZE)

        response = await client.post(
            "/observations",
            content=payload_bytes,
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 422
        data = response.json()
        # The error should mention size/exceeds
        error_text = json.dumps(data).lower()
        assert "exceeds" in error_text or "size" in error_text

    @given(
        fraction=st.floats(min_value=0.01, max_value=0.99),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_payloads_within_1mb_with_valid_fields_are_accepted(
        self, client: AsyncClient, fraction: float
    ) -> None:
        """Payloads <= 1MB with all required fields must be accepted (202)."""
        # Generate a payload that is fraction * MAX_PAYLOAD_SIZE in size
        target_size = int(MAX_PAYLOAD_SIZE * fraction)
        # Ensure minimum viable payload size
        target_size = max(target_size, 200)
        payload_bytes = _make_payload_of_size(target_size)

        # Ensure we don't exceed the limit
        assume(len(payload_bytes) <= MAX_PAYLOAD_SIZE)

        response = await client.post(
            "/observations",
            content=payload_bytes,
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert "job_id" in data


# ---------------------------------------------------------------------------
# Property 2: Observation payload field validation
#
# For any observation payload missing one or more required fields (user_id,
# organization_id, session_id, messages), the system SHALL reject it with a
# validation error that specifies the invalid fields.
# ---------------------------------------------------------------------------


# Strategy: generate a non-empty subset of required fields to omit
omitted_fields_strategy = st.lists(
    st.sampled_from(REQUIRED_FIELDS),
    min_size=1,
    max_size=len(REQUIRED_FIELDS),
    unique=True,
)


class TestProperty2PayloadFieldValidation:
    """Property 2: Observation payload field validation.

    **Validates: Requirements 1.4, 1.5**
    """

    @given(
        fields_to_omit=omitted_fields_strategy,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_missing_required_fields_produce_validation_errors(
        self, client: AsyncClient, fields_to_omit: list[str]
    ) -> None:
        """Missing required fields must produce 422 with errors specifying each missing field."""
        payload = _make_valid_payload()

        # Remove the selected fields
        for field in fields_to_omit:
            del payload[field]

        response = await client.post("/observations", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "errors" in data

        # Each omitted field should appear in the error response
        error_fields = {e["field"] for e in data["errors"]}
        for field in fields_to_omit:
            assert field in error_fields, (
                f"Expected field '{field}' in validation errors, "
                f"got: {error_fields}"
            )

    @given(
        fields_to_nullify=omitted_fields_strategy,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @pytest.mark.asyncio
    async def test_null_required_fields_produce_validation_errors(
        self, client: AsyncClient, fields_to_nullify: list[str]
    ) -> None:
        """Null required fields must produce 422 with errors specifying each null field."""
        payload = _make_valid_payload()

        # Set selected fields to None
        for field in fields_to_nullify:
            payload[field] = None

        response = await client.post("/observations", json=payload)

        assert response.status_code == 422
        data = response.json()
        assert "errors" in data

        # Each nullified field should appear in the error response
        error_fields = {e["field"] for e in data["errors"]}
        for field in fields_to_nullify:
            assert field in error_fields, (
                f"Expected field '{field}' in validation errors, "
                f"got: {error_fields}"
            )
