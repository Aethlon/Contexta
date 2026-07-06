"""Tests for contexta.core.types enums."""

import pytest

from contexta.core.types import (
    EntityType,
    MemoryState,
    MemoryType,
    RelationType,
    SourceType,
    UsageSignal,
)


class TestMemoryType:
    """Verify MemoryType enum members and values."""

    def test_has_all_members(self) -> None:
        expected = {
            "FACT", "PREFERENCE", "GOAL", "PROJECT", "SKILL",
            "RELATIONSHIP", "EVENT", "EPISODIC", "PATTERN",
            "CONTACT", "CUSTOM",
        }
        assert {m.name for m in MemoryType} == expected

    def test_values_are_lowercase(self) -> None:
        for member in MemoryType:
            assert member.value == member.name.lower()

    def test_is_str_enum(self) -> None:
        assert isinstance(MemoryType.FACT, str)
        assert MemoryType.FACT == "fact"


class TestSourceType:
    """Verify SourceType enum members and values."""

    def test_has_all_members(self) -> None:
        expected = {
            "USER_EXPLICIT", "AGENT_INFERENCE", "TOOL_OUTPUT",
            "IMPORTED_FILE", "API",
        }
        assert {m.name for m in SourceType} == expected

    def test_values(self) -> None:
        assert SourceType.USER_EXPLICIT.value == "user_explicit"
        assert SourceType.AGENT_INFERENCE.value == "agent_inference"
        assert SourceType.TOOL_OUTPUT.value == "tool_output"
        assert SourceType.IMPORTED_FILE.value == "imported_file"
        assert SourceType.API.value == "api"


class TestMemoryState:
    """Verify MemoryState enum members and values."""

    def test_has_all_members(self) -> None:
        expected = {"ACTIVE", "WARM", "COLD", "ARCHIVED"}
        assert {m.name for m in MemoryState} == expected

    def test_values(self) -> None:
        assert MemoryState.ACTIVE.value == "active"
        assert MemoryState.WARM.value == "warm"
        assert MemoryState.COLD.value == "cold"
        assert MemoryState.ARCHIVED.value == "archived"


class TestEntityType:
    """Verify EntityType enum members and values."""

    def test_has_all_members(self) -> None:
        expected = {
            "PROJECT", "PERSON", "COMPANY", "TECHNOLOGY",
            "PREFERENCE", "GOAL", "SKILL", "TOPIC",
        }
        assert {m.name for m in EntityType} == expected


class TestRelationType:
    """Verify RelationType enum members and values."""

    def test_has_all_members(self) -> None:
        expected = {
            "USES", "WORKS_ON", "LIKES", "DEPENDS_ON",
            "OWNS", "SUPERSEDED_BY", "RELATED_TO",
        }
        assert {m.name for m in RelationType} == expected

    def test_values(self) -> None:
        assert RelationType.SUPERSEDED_BY.value == "superseded_by"
        assert RelationType.RELATED_TO.value == "related_to"


class TestUsageSignal:
    """Verify UsageSignal enum members and values."""

    def test_has_all_members(self) -> None:
        expected = {"USED", "IGNORED"}
        assert {m.name for m in UsageSignal} == expected

    def test_values(self) -> None:
        assert UsageSignal.USED.value == "used"
        assert UsageSignal.IGNORED.value == "ignored"
