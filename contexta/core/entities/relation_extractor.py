"""Semantic relation extraction and entity typing engine for Contexta knowledge graph.

Extracts typed directional relationships (INTEGRATES_WITH, IS_A, USED_BY, USES,
DEPENDS_ON, WORKS_ON, PART_OF, etc.) between entities from text, and classifies
entities into precise categories while filtering linguistic noise.
"""

from __future__ import annotations

import re
import uuid
from typing import Sequence

from contexta.core.types import EXCLUDED_ENTITY_WORDS, EntityType
from contexta.models.entity import Entity

# Broad vocabulary of generic words that should never be treated as standalone entities
GENERIC_NOISE_WORDS = frozenset({
    "these", "those", "crazy", "thing", "things", "stuff", "work", "job",
    "career", "engine", "architecture", "system", "monitor", "project", "product",
    "feature", "version", "update", "model", "layer", "module", "service",
    "tool", "tools", "library", "code", "file", "data", "database", "query",
    "memory", "memories", "context", "search", "retrieval", "agent", "agents",
    "user", "assistant", "client", "server", "process", "cycle", "state",
    "overview", "summary", "plan", "notes", "status", "decision", "advice",
    "lead", "roles", "candidate", "patent", "cold", "warm", "active",
})

# Curated lookup for canonical technologies, companies, and projects
KNOWN_TECHNOLOGIES = frozenset({
    "python", "rust", "typescript", "javascript", "golang", "c++", "c#",
    "postgres", "postgresql", "redis", "qdrant", "lancedb", "scylladb",
    "docker", "fastapi", "tauri", "react", "nextjs", "next.js", "vue",
    "mcp", "fastembed", "sqlite", "graphql", "rest", "bge", "bm25",
    "sqlalchemy", "asyncpg", "pydantic", "uvicorn", "git", "linux", "cuda",
    "ai", "llm", "ml", "nlp",
})

KNOWN_COMPANIES = frozenset({
    "google", "anthropic", "openai", "microsoft", "apple", "ibm",
    "meta", "wellfound", "yc", "y combinator", "stripe", "supabase",
    "amazon", "aws", "huggingface", "github", "gitlab",
})

KNOWN_PROJECTS = frozenset({
    "contexta", "luno", "nori", "loci", "haru", "tydl", "square",
    "aethlon", "aethlon infra", "memento",
})


def infer_entity_type(name: str, context: str = "") -> EntityType:
    """Classify an entity into a high-level EntityType based on lexicon and context."""
    n_lower = name.lower().strip()
    c_lower = context.lower()

    if n_lower in KNOWN_PROJECTS:
        return EntityType.PROJECT

    if n_lower in KNOWN_TECHNOLOGIES or any(t in n_lower for t in ("db", "sql", "api", "framework", "protocol")):
        return EntityType.TECHNOLOGY

    if n_lower in KNOWN_COMPANIES or any(token in n_lower for token in ("inc", "llc", "corp", "labs", "company")):
        return EntityType.COMPANY

    if "project" in c_lower or "app" in c_lower or "terminal" in c_lower:
        return EntityType.PROJECT

    # Person heuristic: common titles or known first names
    if any(n_lower.startswith(p) for p in ("mr.", "ms.", "dr.", "prof.")):
        return EntityType.PERSON
    if n_lower in {"jenith", "claude", "melanie", "caroline", "alice", "bob", "charlie"}:
        return EntityType.PERSON

    return EntityType.CONCEPT


def filter_entity_candidates(
    candidates: set[str] | list[str],
    text: str,
) -> list[tuple[str, EntityType]]:
    """Filter out common nouns and linguistic false positives, returning validated entities."""
    filtered: list[tuple[str, EntityType]] = []
    seen = set()

    for cand in candidates:
        c_clean = cand.strip().strip("#@.,;:!?()[]\"'")
        c_lower = c_clean.lower()

        # Reject short, excluded, or generic words
        if len(c_clean) < 2:
            continue
        if c_lower in EXCLUDED_ENTITY_WORDS or c_lower in GENERIC_NOISE_WORDS:
            continue
        # Reject generic numbers or dates
        if c_clean.isdigit():
            continue
        # Avoid duplicates
        if c_lower in seen:
            continue

        # Keep acronyms (e.g. AI, ML, DB, YC) or capitalized proper names / known entities
        is_known = (
            c_lower in KNOWN_TECHNOLOGIES
            or c_lower in KNOWN_COMPANIES
            or c_lower in KNOWN_PROJECTS
        )
        is_acronym = c_clean.isupper() and 2 <= len(c_clean) <= 5
        is_capitalized = c_clean[0].isupper() or " " in c_clean

        if is_known or is_acronym or is_capitalized:
            seen.add(c_lower)
            ent_type = infer_entity_type(c_clean, text)
            filtered.append((c_clean, ent_type))

    return filtered


# Ordered relation extraction patterns: (regex_pattern, rel_type_forward, rel_type_backward)
RELATION_PATTERNS = [
    # Integration / connection
    (r"\b(?:integrates\s+with|integrates|connects\s+to|connects\s+with|interfaces\s+with|syncs\s+with)\b", "integrates_with", "integrated_by"),
    # Usage / target audience
    (r"\b(?:used\s+by|built\s+for|designed\s+for|consumed\s+by)\b", "used_by", "uses"),
    (r"\b(?:uses|utilizes|leverages|powers|runs\s+on|built\s+on|built\s+with)\b", "uses", "used_by"),
    # Dependency
    (r"\b(?:depends\s+on|relies\s+(?:on|upon)|requires)\b", "depends_on", "dependency_of"),
    # Work / contribution
    (r"\b(?:works\s+on|develops|building|architecting|maintains)\b", "works_on", "worked_on_by"),
    (r"\b(?:works\s+(?:at|for)|employed\s+(?:at|by)|joined)\b", "works_at", "employs"),
    # Creation / authorship
    (r"\b(?:created\s+by|founded\s+by|authored\s+by|built\s+by)\b", "created_by", "created"),
    # Component / hierarchy
    (r"\b(?:part\s+of|subsystem\s+of|component\s+of|module\s+in|arm\s+of)\b", "part_of", "has_component"),
    # Preferences / sentiment
    (r"\b(?:prefers|likes|loves|favors)\b", "prefers", "preferred_by"),
    (r"\b(?:dislikes|hates|avoids)\b", "avoids", "avoided_by"),
    # Collaboration
    (r"\b(?:collaborates\s+with|partners\s+with|working\s+with)\b", "collaborates_with", "collaborates_with"),
    # Location
    (r"\b(?:located\s+in|based\s+in|lives\s+in)\b", "located_in", "location_of"),
    # Class / role identification
    (r"\b(?:is\s+(?:an?|the)?\s*|acts\s+as\s+(?:an?|the)?\s*|serves\s+as\s+(?:an?|the)?\s*)\b", "is_a", "has_instance"),
]


def extract_semantic_relations(
    text: str,
    entities: Sequence[Entity],
) -> list[tuple[Entity, str, Entity]]:
    """Analyze sentence grammar and text between entity pairs to extract typed relationships.

    Returns a list of (source_entity, relationship_type, target_entity).
    """
    if len(entities) < 2:
        return []

    # Map entity ID pair (frozenset) -> (source_entity, rel_type, target_entity)
    matched_specific: dict[frozenset[uuid.UUID], tuple[Entity, str, Entity]] = {}

    # Split text into distinct sentences and lines
    sentences: list[str] = []
    for line in text.splitlines():
        line_clean = line.strip()
        if line_clean:
            for s in re.split(r"(?<=[.!?])\s+", line_clean):
                s_strip = s.strip()
                if s_strip:
                    sentences.append(s_strip)

    for sent in sentences:
        s_lower = sent.lower()

        # Find all occurrences of each entity in this sentence
        present_entities: list[tuple[int, Entity]] = []
        for ent in entities:
            matches = list(re.finditer(r"\b" + re.escape(ent.name.lower()) + r"\b", s_lower))
            for m in matches:
                present_entities.append((m.start(), ent))

        present_entities.sort(key=lambda x: x[0])

        # Test entity pairs in this sentence
        for i in range(len(present_entities)):
            for j in range(i + 1, len(present_entities)):
                pos_a, ent_a = present_entities[i]
                pos_b, ent_b = present_entities[j]

                if ent_a.id == ent_b.id:
                    continue

                pair_key = frozenset({ent_a.id, ent_b.id})

                # Span between ent_a and ent_b
                len_a = len(ent_a.name)
                between_span = s_lower[pos_a + len_a : pos_b].strip()

                # If distance between entities is reasonable (up to 16 words)
                if len(between_span.split()) <= 16:
                    for pattern, forward_rel, backward_rel in RELATION_PATTERNS:
                        if re.search(pattern, between_span):
                            matched_specific[pair_key] = (ent_a, forward_rel, ent_b)
                            break

    # Build final list: specific relations take absolute priority
    relations: list[tuple[Entity, str, Entity]] = list(matched_specific.values())
    covered_pairs = set(matched_specific.keys())

    # Fallback to related_to for unlinked pairs that co-occur in the same memory
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            ea = entities[i]
            eb = entities[j]
            if ea.id != eb.id:
                pair = frozenset({ea.id, eb.id})
                if pair not in covered_pairs:
                    relations.append((ea, "related_to", eb))
                    covered_pairs.add(pair)

    return relations
