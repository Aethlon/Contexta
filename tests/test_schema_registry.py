"""Tests for custom schema registry."""

from uuid import uuid4

import pytest

from contexta.core.errors import ValidationError
from contexta.core.schema_registry.registry import SchemaRegistry


def valid_schema() -> dict:
    return {
        "fields": [
            {"name": "company", "type": "string"},
            {"name": "amount", "type": "number"},
            {"name": "stage", "type": "enum", "values": ["lead", "won"]},
            {"name": "tags", "type": "array"},
        ],
        "required": ["company", "stage"],
    }


async def test_register_and_get_schema_round_trip() -> None:
    organization_id = uuid4()
    registry = SchemaRegistry()

    registered = await registry.register(
        organization_id,
        "deal",
        valid_schema(),
    )

    assert registry.get(organization_id, "deal") == registered


async def test_duplicate_fields_are_rejected() -> None:
    registry = SchemaRegistry()
    schema = {
        "fields": [
            {"name": "company", "type": "string"},
            {"name": "company", "type": "number"},
        ],
        "required": [],
    }

    with pytest.raises(ValidationError):
        await registry.register(uuid4(), "bad", schema)


async def test_invalid_field_type_is_rejected() -> None:
    registry = SchemaRegistry()
    schema = {
        "fields": [{"name": "company", "type": "blob"}],
        "required": [],
    }

    with pytest.raises(ValidationError):
        await registry.register(uuid4(), "bad", schema)


async def test_extract_with_schema_returns_structured_data_when_valid() -> None:
    organization_id = uuid4()
    registry = SchemaRegistry()
    await registry.register(organization_id, "deal", valid_schema())

    result = registry.extract_with_schema(
        organization_id=organization_id,
        schema_name="deal",
        raw_content="Acme deal is won.",
        extracted_data={
            "company": "Acme",
            "amount": 1000,
            "stage": "won",
            "tags": ["priority"],
        },
    )

    assert result.structured_data == {
        "company": "Acme",
        "amount": 1000,
        "stage": "won",
        "tags": ["priority"],
    }
    assert result.flag_for_review is False
    assert result.field_mapping == {
        "company": "company",
        "amount": "amount",
        "stage": "stage",
        "tags": "tags",
    }


async def test_validation_failure_falls_back_to_raw_content() -> None:
    organization_id = uuid4()
    registry = SchemaRegistry()
    await registry.register(organization_id, "deal", valid_schema())

    result = registry.extract_with_schema(
        organization_id=organization_id,
        schema_name="deal",
        raw_content="Acme deal has unknown stage.",
        extracted_data={"company": "Acme", "stage": "maybe"},
    )

    assert result.structured_data is None
    assert result.raw_content == "Acme deal has unknown stage."
    assert result.flag_for_review is True
    assert result.errors == ["stage must be enum"]
