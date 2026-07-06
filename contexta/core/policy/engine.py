"""Policy engine for extraction store/ignore rules."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from contexta.core.policy.templates import BUILTIN_TEMPLATES
from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryType
from contexta.models.policy import MemoryPolicy


class PolicyRepository(Protocol):
    async def create(self, record: MemoryPolicy) -> MemoryPolicy:
        ...


@dataclass
class PolicyDefinition:
    """Extraction policy definition."""

    name: str
    store_memory_types: set[MemoryType] = field(default_factory=lambda: set(MemoryType))
    ignore_patterns: list[str] = field(default_factory=list)
    priority_weights: dict[MemoryType, float] = field(default_factory=dict)
    is_builtin: bool = False


@dataclass
class PolicyApplication:
    """Output of applying a policy."""

    accepted: list[ExtractedMemory]
    rejected: list[ExtractedMemory]


class PolicyEngine:
    """Register and apply tenant-scoped extraction policies."""

    def __init__(self, repository: PolicyRepository | None = None) -> None:
        self._repository = repository
        self._policies: dict[tuple[uuid.UUID, str], PolicyDefinition] = {}
        self._default_policy = PolicyDefinition(name="default")

    async def register_policy(
        self,
        organization_id: uuid.UUID,
        policy: PolicyDefinition,
    ) -> PolicyDefinition:
        """Register a tenant-scoped named policy."""
        self._policies[(organization_id, policy.name)] = policy
        if self._repository is not None:
            await self._repository.create(
                MemoryPolicy(
                    organization_id=organization_id,
                    name=policy.name,
                    store_rules={
                        "memory_types": [
                            memory_type.value
                            for memory_type in sorted(
                                policy.store_memory_types,
                                key=lambda item: item.value,
                            )
                        ]
                    },
                    ignore_rules={"patterns": policy.ignore_patterns},
                    priority_weights={
                        memory_type.value: weight
                        for memory_type, weight in policy.priority_weights.items()
                    },
                    is_builtin=policy.is_builtin,
                )
            )
        return policy

    def get_policy(
        self,
        organization_id: uuid.UUID,
        name: str | None,
    ) -> PolicyDefinition:
        """Return a registered or built-in policy, falling back to default."""
        if not name:
            return self._default_policy
        if (organization_id, name) in self._policies:
            return self._policies[(organization_id, name)]
        if name in BUILTIN_TEMPLATES:
            return self.from_template(name)
        return self._default_policy

    def apply_policy(
        self,
        policy: PolicyDefinition,
        memories: list[ExtractedMemory],
    ) -> PolicyApplication:
        """Filter memories by store and ignore rules."""
        accepted: list[ExtractedMemory] = []
        rejected: list[ExtractedMemory] = []
        ignore_patterns = [re.compile(pattern, re.I) for pattern in policy.ignore_patterns]

        for memory in memories:
            if memory.memory_type not in policy.store_memory_types:
                rejected.append(memory)
                continue
            if any(pattern.search(memory.content) for pattern in ignore_patterns):
                rejected.append(memory)
                continue
            accepted.append(memory)

        return PolicyApplication(accepted=accepted, rejected=rejected)

    def priority_weight(
        self,
        policy: PolicyDefinition,
        memory_type: MemoryType,
        default: float,
    ) -> float:
        """Return policy override weight or default score."""
        return policy.priority_weights.get(memory_type, default)

    def from_template(
        self,
        name: str,
        *,
        store_memory_types: set[MemoryType] | None = None,
        ignore_patterns: list[str] | None = None,
        priority_weights: dict[MemoryType, float] | None = None,
    ) -> PolicyDefinition:
        """Create a built-in policy, optionally extended with custom rules."""
        template = BUILTIN_TEMPLATES[name]
        store_types = {
            MemoryType(value) for value in template["store"]["memory_types"]
        }
        if store_memory_types:
            store_types.update(store_memory_types)

        patterns = list(template["ignore"]["patterns"])
        if ignore_patterns:
            patterns.extend(ignore_patterns)

        weights = {
            MemoryType(value): weight
            for value, weight in template["priority_weights"].items()
        }
        if priority_weights:
            weights.update(priority_weights)

        return PolicyDefinition(
            name=name,
            store_memory_types=store_types,
            ignore_patterns=patterns,
            priority_weights=weights,
            is_builtin=True,
        )
