"""Core enums and type definitions for the contexta memory engine."""

from enum import Enum


class MemoryType(str, Enum):
    """Classification of memory content type."""

    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    PROJECT = "project"
    SKILL = "skill"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    EPISODIC = "episodic"
    PATTERN = "pattern"
    CONTACT = "contact"
    CUSTOM = "custom"


class SourceType(str, Enum):
    """Origin classification for extracted memories."""

    USER_EXPLICIT = "user_explicit"
    AGENT_INFERENCE = "agent_inference"
    TOOL_OUTPUT = "tool_output"
    IMPORTED_FILE = "imported_file"
    API = "api"


class MemoryState(str, Enum):
    """Lifecycle state of a memory record."""

    ACTIVE = "active"
    WARM = "warm"
    COLD = "cold"
    ARCHIVED = "archived"


class EntityType(str, Enum):
    """Classification of entities in the knowledge graph."""

    PROJECT = "project"
    PERSON = "person"
    COMPANY = "company"
    TECHNOLOGY = "technology"
    PREFERENCE = "preference"
    GOAL = "goal"
    SKILL = "skill"
    TOPIC = "topic"


class RelationType(str, Enum):
    """Typed edges between entities in the knowledge graph."""

    USES = "uses"
    WORKS_ON = "works_on"
    LIKES = "likes"
    DEPENDS_ON = "depends_on"
    OWNS = "owns"
    SUPERSEDED_BY = "superseded_by"
    RELATED_TO = "related_to"


class UsageSignal(str, Enum):
    """Signal indicating whether a retrieved memory was used by the agent."""

    USED = "used"
    IGNORED = "ignored"
