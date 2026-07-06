"""Tests for contexta.core.errors base error classes."""

import pytest

from contexta.core.errors import (
    AuthorizationError,
    ExtractionError,
    contextaError,
    StorageError,
    ValidationError,
)


class TestcontextaError:
    """Verify base contextaError behavior."""

    def test_default_message(self) -> None:
        err = contextaError()
        assert err.message == "An error occurred in contexta."
        assert str(err) == "An error occurred in contexta."

    def test_custom_message(self) -> None:
        err = contextaError("Something went wrong")
        assert err.message == "Something went wrong"

    def test_is_exception(self) -> None:
        with pytest.raises(contextaError):
            raise contextaError("test")


class TestValidationError:
    """Verify ValidationError with field tracking."""

    def test_default(self) -> None:
        err = ValidationError()
        assert err.message == "Validation failed."
        assert err.fields == []

    def test_with_fields(self) -> None:
        err = ValidationError("Missing fields", fields=["user_id", "session_id"])
        assert err.fields == ["user_id", "session_id"]
        assert err.message == "Missing fields"

    def test_inherits_CONTEXTA_error(self) -> None:
        err = ValidationError()
        assert isinstance(err, contextaError)

    def test_catchable_as_CONTEXTA_error(self) -> None:
        with pytest.raises(contextaError):
            raise ValidationError("bad input", fields=["org_id"])


class TestAuthorizationError:
    """Verify AuthorizationError behavior."""

    def test_default_message(self) -> None:
        err = AuthorizationError()
        assert err.message == "Authorization denied."

    def test_custom_message(self) -> None:
        err = AuthorizationError("Cross-tenant access denied")
        assert err.message == "Cross-tenant access denied"

    def test_inherits_CONTEXTA_error(self) -> None:
        assert isinstance(AuthorizationError(), contextaError)


class TestExtractionError:
    """Verify ExtractionError with observation tracking."""

    def test_default(self) -> None:
        err = ExtractionError()
        assert err.message == "Memory extraction failed."
        assert err.observation_id is None

    def test_with_observation_id(self) -> None:
        err = ExtractionError("LLM timeout", observation_id="obs-123")
        assert err.observation_id == "obs-123"
        assert err.message == "LLM timeout"

    def test_inherits_CONTEXTA_error(self) -> None:
        assert isinstance(ExtractionError(), contextaError)


class TestStorageError:
    """Verify StorageError with operation tracking."""

    def test_default(self) -> None:
        err = StorageError()
        assert err.message == "Storage operation failed."
        assert err.operation is None

    def test_with_operation(self) -> None:
        err = StorageError("Connection refused", operation="insert")
        assert err.operation == "insert"
        assert err.message == "Connection refused"

    def test_inherits_CONTEXTA_error(self) -> None:
        assert isinstance(StorageError(), contextaError)
