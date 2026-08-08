"""Tests for extraction policy engine."""

from uuid import uuid4

from contexta.core.policy.engine import PolicyDefinition, PolicyEngine
from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryType, SourceType


def memory(memory_type: MemoryType, content: str = "Useful content") -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=memory_type,
        source_type=SourceType.USER_EXPLICIT,
        title="Memory",
        content=content,
    )


async def test_register_then_get_returns_policy() -> None:
    organization_id = uuid4()
    engine = PolicyEngine()
    policy = PolicyDefinition(
        name="custom",
        store_memory_types={MemoryType.FACT},
        ignore_patterns=["ignore me"],
    )

    await engine.register_policy(organization_id, policy)

    assert engine.get_policy(organization_id, "custom") is policy


def test_default_policy_allows_all_memory_types() -> None:
    engine = PolicyEngine()
    policy = engine.get_policy(uuid4(), None)

    assert policy.store_memory_types == set(MemoryType)


def test_apply_policy_enforces_store_and_ignore_rules() -> None:
    engine = PolicyEngine()
    policy = PolicyDefinition(
        name="focused",
        store_memory_types={MemoryType.FACT},
        ignore_patterns=[r"do not store"],
    )
    fact = memory(MemoryType.FACT)
    ignored = memory(MemoryType.FACT, "do not store this")
    preference = memory(MemoryType.PREFERENCE)

    result = engine.apply_policy(policy, [fact, ignored, preference])

    assert result.accepted == [fact]
    assert result.rejected == [ignored, preference]


def test_priority_weight_override() -> None:
    engine = PolicyEngine()
    policy = PolicyDefinition(
        name="weighted",
        priority_weights={MemoryType.PROJECT: 0.95},
    )

    assert engine.priority_weight(policy, MemoryType.PROJECT, 0.8) == 0.95
    assert engine.priority_weight(policy, MemoryType.FACT, 0.45) == 0.45


def test_template_extension_contains_base_and_custom_rules() -> None:
    engine = PolicyEngine()
    policy = engine.from_template(
        "coding-agent",
        store_memory_types={MemoryType.CONTACT},
        ignore_patterns=["scratchpad"],
        priority_weights={MemoryType.CONTACT: 0.6},
    )

    assert MemoryType.PROJECT in policy.store_memory_types
    assert MemoryType.CONTACT in policy.store_memory_types
    assert "scratchpad" in policy.ignore_patterns
    assert policy.priority_weights[MemoryType.CONTACT] == 0.6
