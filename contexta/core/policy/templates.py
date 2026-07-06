"""Built-in policy templates."""

from contexta.core.types import MemoryType


BUILTIN_TEMPLATES = {
    "coding-agent": {
        "store": {
            "memory_types": [
                MemoryType.PROJECT.value,
                MemoryType.FACT.value,
                MemoryType.PREFERENCE.value,
                MemoryType.SKILL.value,
                MemoryType.GOAL.value,
                MemoryType.PATTERN.value,
            ]
        },
        "ignore": {"patterns": [r"^\s*(thanks|ok|cool)\s*$"]},
        "priority_weights": {
            MemoryType.PROJECT.value: 0.9,
            MemoryType.SKILL.value: 0.75,
        },
    },
    "crm-agent": {
        "store": {
            "memory_types": [
                MemoryType.CONTACT.value,
                MemoryType.RELATIONSHIP.value,
                MemoryType.PREFERENCE.value,
                MemoryType.EVENT.value,
                MemoryType.FACT.value,
            ]
        },
        "ignore": {"patterns": [r"^\s*(hello|hi|thanks)\s*$"]},
        "priority_weights": {
            MemoryType.CONTACT.value: 0.9,
            MemoryType.RELATIONSHIP.value: 0.8,
        },
    },
    "tutor-agent": {
        "store": {
            "memory_types": [
                MemoryType.SKILL.value,
                MemoryType.GOAL.value,
                MemoryType.PREFERENCE.value,
                MemoryType.PATTERN.value,
                MemoryType.FACT.value,
            ]
        },
        "ignore": {"patterns": [r"^\s*(yes|no|ok|thanks)\s*$"]},
        "priority_weights": {
            MemoryType.GOAL.value: 0.85,
            MemoryType.SKILL.value: 0.8,
        },
    },
}
