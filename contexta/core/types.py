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
    PROCEDURAL = "procedural"
    RULE = "rule"
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
    CONCEPT = "concept"


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


EXCLUDED_ENTITY_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "this", "that", "these", "those",
    "i", "me", "my", "we", "us", "our", "you", "your", "he", "him", "his",
    "she", "her", "they", "them", "their", "it", "its",
    "what", "when", "where", "who", "which", "whose", "why", "how",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "having",
    "would", "could", "should", "will", "can", "may", "might", "must",
    "and", "or", "but", "if", "so", "then", "because", "as", "until", "while",
    "of", "at", "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further",
    "there", "here", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "too", "very",
    "yeah", "yes", "nope", "hey", "good", "great", "thanks", "thank", "date",
    "gonna", "wanna", "gotta", "yesterday", "today", "tomorrow", "sure", "well",
    "just", "also", "wow", "hope", "congrats", "nothing", "anything", "something",
    "maybe", "actually", "really", "since", "even", "speaker", "user", "time",
    "day", "week", "month", "year", "lot", "lots", "thing", "things", "stuff", "mel",
})
