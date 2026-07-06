"""Tenant-scoped custom schema registry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from contexta.core.errors import ValidationError
from contexta.models.schema import CustomSchema


class SchemaRepository(Protocol):
    async def create(self, record: CustomSchema) -> CustomSchema:
        ...


VALID_FIELD_TYPES = {"string", "number", "boolean", "date", "enum", "array", "object"}


@dataclass(frozen=True)
class SchemaExtractionResult:
    """Result of validating extracted data against a custom schema."""

    structured_data: dict[str, Any] | None
    raw_content: str
    flag_for_review: bool
    schema_name: str
    field_mapping: dict[str, str]
    errors: list[str]


class SchemaRegistry:
    """Register and validate tenant-scoped custom memory schemas."""

    def __init__(self, repository: SchemaRepository | None = None) -> None:
        self._repository = repository
        self._schemas: dict[tuple[uuid.UUID, str], dict[str, Any]] = {}

    async def register(
        self,
        organization_id: uuid.UUID,
        name: str,
        field_definitions: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and register a schema."""
        self._validate_schema(field_definitions)
        self._schemas[(organization_id, name)] = field_definitions
        if self._repository is not None:
            await self._repository.create(
                CustomSchema(
                    organization_id=organization_id,
                    name=name,
                    field_definitions=field_definitions,
                )
            )
        return field_definitions

    def get(self, organization_id: uuid.UUID, name: str) -> dict[str, Any] | None:
        """Retrieve a registered tenant schema."""
        return self._schemas.get((organization_id, name))

    def extract_with_schema(
        self,
        *,
        organization_id: uuid.UUID,
        schema_name: str,
        raw_content: str,
        extracted_data: dict[str, Any],
    ) -> SchemaExtractionResult:
        """Validate extracted data and fall back to raw content on failure."""
        schema = self.get(organization_id, schema_name)
        if schema is None:
            raise ValidationError("Schema not found.", fields=["schema_name"])

        errors = self._validate_data(schema, extracted_data)
        if errors:
            return SchemaExtractionResult(
                structured_data=None,
                raw_content=raw_content,
                flag_for_review=True,
                schema_name=schema_name,
                field_mapping={},
                errors=errors,
            )

        return SchemaExtractionResult(
            structured_data=extracted_data,
            raw_content=raw_content,
            flag_for_review=False,
            schema_name=schema_name,
            field_mapping={field["name"]: field["name"] for field in schema["fields"]},
            errors=[],
        )

    def _validate_schema(self, schema: dict[str, Any]) -> None:
        fields = schema.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ValidationError("Schema requires a non-empty fields list.", ["fields"])

        names: set[str] = set()
        for index, field in enumerate(fields):
            if not isinstance(field, dict):
                raise ValidationError("Schema field must be an object.", [f"fields[{index}]"])
            name = field.get("name")
            field_type = field.get("type")
            if not name or not isinstance(name, str):
                raise ValidationError("Schema field requires a name.", [f"fields[{index}].name"])
            if name in names:
                raise ValidationError("Duplicate schema field name.", [name])
            names.add(name)
            if field_type not in VALID_FIELD_TYPES:
                raise ValidationError("Invalid schema field type.", [name])
            if field_type == "enum" and not field.get("values"):
                raise ValidationError("Enum field requires values.", [name])

        required = schema.get("required", [])
        if not isinstance(required, list):
            raise ValidationError("Schema required must be a list.", ["required"])
        missing = [name for name in required if name not in names]
        if missing:
            raise ValidationError("Required field is not defined.", missing)

    def _validate_data(
        self,
        schema: dict[str, Any],
        data: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        fields = {field["name"]: field for field in schema["fields"]}

        for name in schema.get("required", []):
            if name not in data or data[name] is None:
                errors.append(f"{name} is required")

        for name, value in data.items():
            field = fields.get(name)
            if field is None:
                continue
            if not self._matches_type(value, field):
                errors.append(f"{name} must be {field['type']}")

        return errors

    def _matches_type(self, value: Any, field: dict[str, Any]) -> bool:
        field_type = field["type"]
        if value is None:
            return True
        if field_type == "string":
            return isinstance(value, str)
        if field_type == "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        if field_type == "boolean":
            return isinstance(value, bool)
        if field_type == "date":
            if isinstance(value, date | datetime):
                return True
            if isinstance(value, str):
                try:
                    date.fromisoformat(value)
                    return True
                except ValueError:
                    return False
            return False
        if field_type == "enum":
            return value in field.get("values", [])
        if field_type == "array":
            return isinstance(value, list)
        if field_type == "object":
            return isinstance(value, dict)
        return False
