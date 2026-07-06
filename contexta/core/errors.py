"""Base error classes for the contexta memory engine."""


class contextaError(Exception):
    """Base exception for all contexta errors."""

    def __init__(self, message: str = "An error occurred in contexta.") -> None:
        self.message = message
        super().__init__(self.message)


class ValidationError(contextaError):
    """Raised when input validation fails (e.g., missing fields, size limits)."""

    def __init__(
        self,
        message: str = "Validation failed.",
        fields: list[str] | None = None,
    ) -> None:
        self.fields = fields or []
        super().__init__(message)


class AuthorizationError(contextaError):
    """Raised when a tenant or user attempts an unauthorized operation."""

    def __init__(
        self,
        message: str = "Authorization denied.",
    ) -> None:
        super().__init__(message)


class ExtractionError(contextaError):
    """Raised when memory extraction from an observation fails."""

    def __init__(
        self,
        message: str = "Memory extraction failed.",
        observation_id: str | None = None,
    ) -> None:
        self.observation_id = observation_id
        super().__init__(message)


class StorageError(contextaError):
    """Raised when a storage operation (read/write) fails."""

    def __init__(
        self,
        message: str = "Storage operation failed.",
        operation: str | None = None,
    ) -> None:
        self.operation = operation
        super().__init__(message)
