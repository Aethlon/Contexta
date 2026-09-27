"""Contexta Cortex engine: the decision and routing brain of Contexta.

Coordinates JEV System One queries on both the write (ingestion) and read (retrieval)
paths with automatic heuristic fallbacks and telemetry tracking.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from contexta.config.settings import Settings, get_settings
from contexta.core.cortex.client import JevClient
from contexta.core.cortex.decisions import (
    CortexReadDecision,
    CortexTelemetry,
    CortexWriteDecision,
)
from contexta.core.schemas import ObservationPayload, RetrievalQuery

logger = logging.getLogger(__name__)

GREETING_WORDS = {
    "hi", "hello", "hey", "thanks", "thank", "you", "thx", "ok", "okay",
    "cool", "k", "bye", "goodbye", "see", "ya", "good", "morning",
    "afternoon", "evening", "there", "yes", "no", "yep", "nope", "great",
    "sure", "welcome",
}


class ContextaCortex:
    """Contexta Cortex: typed decision and routing layer powered by JEV."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: JevClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or JevClient(
            api_key=self._settings.jev_api_key,
            base_url=self._settings.jev_base_url,
            model=self._settings.jev_model,
            timeout_seconds=self._settings.jev_timeout_seconds,
        )

    @property
    def is_enabled(self) -> bool:
        """Return True if the Cortex feature is enabled."""
        return bool(self._settings.feature_cortex)

    def _remote_enabled(self) -> bool:
        return bool(
            str(getattr(self._settings, "engine_mode", "offline")).lower() == "online"
            and self._settings.jev_api_key
        )

    # ── WRITE PATH: INGESTION EVALUATION ────────────────────────────────

    async def evaluate_observation(
        self,
        payload: ObservationPayload,
    ) -> CortexWriteDecision:
        """Evaluate an incoming observation to produce an advisory write decision.

        Determines if the observation should be stored, its category, importance,
        and extraction guidance.
        """
        if not self.is_enabled:
            return CortexWriteDecision(
                should_store=True,
                store_probability=1.0,
                suggested_memory_type="fact",
                importance_score=0.5,
                derived_summary="Cortex disabled via feature flag",
                telemetry=CortexTelemetry(latency_ms=0.0, source="disabled"),
            )

        # Extract normalized state representation from observation messages
        state = self._format_observation_state(payload)
        if not state.strip():
            return CortexWriteDecision(
                should_store=False,
                store_probability=0.0,
                derived_summary="Empty observation text",
                telemetry=CortexTelemetry(latency_ms=0.0, source="heuristic_fallback"),
            )

        if not self._remote_enabled():
            return self._heuristic_write_decision(
                state,
                CortexTelemetry(latency_ms=0.0, source="heuristic_fallback"),
            )

        questions = {
            "should_store": {
                "type": "noul",
                "instructions": (
                    "Does this observation contain meaningful, durable user facts, "
                    "preferences, decisions, goals, or rules worth remembering long-term? "
                    "(Reject conversational greetings, trivial acknowledgments, or ephemeral chit-chat)"
                ),
            },
            "memory_type": {
                "type": "choice",
                "instructions": "What primary memory category does this observation represent?",
                "criteria": {
                    "preference": "User likes, dislikes, personal tastes, styles, workflows",
                    "fact": "Objective facts, user attributes, credentials, tools used, environment",
                    "decision": "Explicit choices, architectural decisions, selected frameworks",
                    "goal": "User targets, project objectives, milestones",
                    "event": "Calendar events, meetings, incidents, historical timeline",
                    "rule": "System rules, instructions, behavioral constraints",
                },
            },
            "importance": {
                "type": "score",
                "instructions": "Rate how critical this knowledge is to future interactions on an ordered scale",
                "criteria": [
                    "Trivial, transient detail, pleasantry, or fleeting statement",
                    "Standard operational fact, moderate preference, or typical workflow detail",
                    "Critical architectural decision, core user constraint, or hard system invariant",
                ],
            },
            "is_update": {
                "type": "noul",
                "instructions": "Does this statement update, correct, modify, or contradict an earlier statement or previous configuration?",
            },
            "needs_temporal": {
                "type": "noul",
                "instructions": "Does this information have time-bounds, deadlines, dates, or chronological significance?",
            },
            "needs_entity_rel": {
                "type": "noul",
                "instructions": "Does this involve relationships between multiple entities (e.g. person-to-project, tool-to-language)?",
            },
            "extraction_depth": {
                "type": "choice",
                "instructions": "Is normal fast extraction sufficient, or is this complex requiring deep extraction?",
                "criteria": {
                    "normal": "Standard single-turn fact, straightforward preference",
                    "deep": "Complex multi-paragraph specification, dense relationships, ambiguous nuances",
                },
            },
        }

        raw_data, telemetry = await self._client.evaluate(state, questions)

        if raw_data is not None:
            return CortexWriteDecision.from_jev_response(raw_data, telemetry)

        # Fallback to local heuristic when JEV is unreachable or fails
        return self._heuristic_write_decision(state, telemetry)

    # ── READ PATH: RETRIEVAL ROUTING ────────────────────────────────────

    async def classify_query(
        self,
        query: RetrievalQuery,
    ) -> CortexReadDecision:
        """Classify query intent to dynamically guide hybrid retrieval layers."""
        if not self.is_enabled:
            return CortexReadDecision(
                strategy="hybrid",
                requires_graph=False,
                requires_temporal_filter=False,
                priority_memory_type=None,
                derived_summary="Cortex disabled via feature flag",
                telemetry=CortexTelemetry(latency_ms=0.0, source="disabled"),
            )

        state = query.query_text.strip()
        if not state:
            return CortexReadDecision(
                strategy="hybrid",
                derived_summary="Empty query text",
                telemetry=CortexTelemetry(latency_ms=0.0, source="heuristic_fallback"),
            )

        if not self._remote_enabled():
            return self._heuristic_read_decision(
                state,
                CortexTelemetry(latency_ms=0.0, source="heuristic_fallback"),
            )

        questions = {
            "retrieval_strategy": {
                "type": "choice",
                "instructions": "Which retrieval strategy best answers this query?",
                "criteria": {
                    "hybrid": "General query needing balanced conceptual and keyword recall",
                    "semantic": "Conceptual, abstract, fuzzy thematic question",
                    "exact": "Exact identifier, acronym, code token, error message, exact phrase",
                    "graph": "Questions about relationships, who works with whom, dependencies between entities",
                    "temporal": "Timeline, history, when something happened, sequence of events",
                },
            },
            "requires_graph": {
                "type": "noul",
                "instructions": "Does answering this query require traversing entity relationships across multiple hops?",
            },
            "requires_temporal_filter": {
                "type": "noul",
                "instructions": "Does this query ask about recent changes, timeline order, or specific dates?",
            },
            "priority_memory_type": {
                "type": "choice",
                "instructions": "Is the user specifically asking for a particular category of memory?",
                "criteria": {
                    "any": "General query or unconstrained",
                    "preference": "Asking what the user prefers, likes, dislikes",
                    "decision": "Asking what was chosen, decided, or agreed upon",
                    "fact": "Asking for specific factual info or technical spec",
                    "rule": "Asking about constraints, conventions, or instructions",
                },
            },
        }

        raw_data, telemetry = await self._client.evaluate(state, questions)

        if raw_data is not None:
            return CortexReadDecision.from_jev_response(raw_data, telemetry)

        return self._heuristic_read_decision(state, telemetry)

    # ── HEURISTIC FALLBACK ENGINES ──────────────────────────────────────

    def _heuristic_write_decision(
        self,
        state: str,
        telemetry: CortexTelemetry,
    ) -> CortexWriteDecision:
        """Deterministic local heuristic when JEV is unavailable."""
        telemetry.source = "heuristic_fallback"
        cleaned = state.strip()

        # Strip common role prefixes like "user: ", "assistant: "
        unprefixed = re.sub(r"^(user|assistant|system)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()

        # Check for pure trivial chit-chat / greetings
        words = re.findall(r"[a-z]+", unprefixed.lower())
        is_greeting = words and all(w in GREETING_WORDS for w in words) and len(words) <= 6
        if is_greeting or len(unprefixed) < 6:
            return CortexWriteDecision(
                should_store=False,
                store_probability=0.1,
                suggested_memory_type="fact",
                importance_score=0.1,
                derived_summary="Heuristic fallback: Ephemeral greeting/chit-chat",
                telemetry=telemetry,
            )

        lower = cleaned.lower()

        # Memory Type Heuristic
        suggested_type = "fact"
        if any(w in lower for w in ("prefer", "like", "hate", "love", "favorite", "style", "taste", "rather")):
            suggested_type = "preference"
        elif any(w in lower for w in ("decide", "decided", "chose", "chosen", "selected", "agree", "architect")):
            suggested_type = "decision"
        elif any(w in lower for w in ("goal", "aim", "target", "milestone", "plan to", "want to achieve")):
            suggested_type = "goal"
        elif any(w in lower for w in ("must", "always", "never", "rule", "convention", "invariant")):
            suggested_type = "rule"
        elif any(w in lower for w in ("meeting", "incident", "deployed", "event", "yesterday", "tomorrow")):
            suggested_type = "event"

        # Update detection
        is_update = any(w in lower for w in ("no longer", "update", "changed", "switched to", "instead of", "replace"))

        # Temporal detection
        needs_temporal = any(w in lower for w in ("until", "deadline", "by next", "date", "202", "schedule", "at 5"))

        # Entity relationship detection
        needs_entity_rel = any(w in lower for w in ("with", "works on", "leads", "integrates with", "belongs to"))

        # Importance estimation
        importance = 0.7 if (suggested_type in ("preference", "decision", "rule") or is_update) else 0.5

        # Depth
        depth = "deep" if len(cleaned.split()) > 100 or "\n\n" in cleaned else "normal"

        summary = (
            f"Heuristic fallback: store=True, type={suggested_type}, "
            f"importance={importance:.2f}, update={is_update}, depth={depth}"
        )

        return CortexWriteDecision(
            should_store=True,
            store_probability=0.85,
            suggested_memory_type=suggested_type,
            importance_score=importance,
            is_update=is_update,
            needs_temporal=needs_temporal,
            needs_entity_rel=needs_entity_rel,
            extraction_depth=depth,
            derived_summary=summary,
            telemetry=telemetry,
        )

    def _heuristic_read_decision(
        self,
        query: str,
        telemetry: CortexTelemetry,
    ) -> CortexReadDecision:
        """Deterministic local heuristic query classification."""
        telemetry.source = "heuristic_fallback"
        lower = query.lower()

        # Exact Match indicators: code tokens, error codes, UUIDs, quotes
        has_code_or_quotes = bool(re.search(r"[`'\"][^`'\"]+[`'\"]", query))
        has_error_code = bool(re.search(r"\b(4\d\d|5\d\d|[a-z0-9_-]{8,}|err_)\b", lower))
        if has_code_or_quotes or has_error_code or "exact" in lower:
            strategy = "exact"
        # Graph indicators: relationships, people, organizations, connections
        elif any(w in lower for w in ("who", "whom", "team", "organization", "connect", "relate", "works with", "leads")):
            strategy = "graph"
        # Temporal indicators: timelines, sequence, dates
        elif any(w in lower for w in ("when", "timeline", "history", "recent", "latest", "first", "last week", "yesterday")):
            strategy = "temporal"
        # Conceptual / Semantic
        elif any(w in lower for w in ("why", "how", "concept", "similar", "explain")):
            strategy = "semantic"
        else:
            strategy = "hybrid"

        requires_graph = strategy == "graph" or any(w in lower for w in ("lead", "member", "relation", "team"))
        requires_temporal = strategy == "temporal" or any(w in lower for w in ("recent", "latest", "date", "when"))

        priority_type = None
        if "prefer" in lower or "like" in lower:
            priority_type = "preference"
        elif "decid" in lower or "choice" in lower:
            priority_type = "decision"
        elif "rule" in lower or "convention" in lower:
            priority_type = "rule"

        summary = (
            f"Heuristic fallback: strategy={strategy}, graph={requires_graph}, "
            f"temporal={requires_temporal}, priority_type={priority_type or 'all'}"
        )

        return CortexReadDecision(
            strategy=strategy,
            requires_graph=requires_graph,
            requires_temporal_filter=requires_temporal,
            priority_memory_type=priority_type,
            derived_summary=summary,
            telemetry=telemetry,
        )

    # ── HELPERS ──────────────────────────────────────────────────────────

    def _format_observation_state(self, payload: ObservationPayload) -> str:
        """Format an observation payload into a concise text state for JEV."""
        lines: list[str] = []
        for msg in payload.messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                text = msg.get("text") or msg.get("content") or ""
                if text:
                    lines.append(f"{role}: {text}")
            elif isinstance(msg, str):
                lines.append(msg)
        return "\n".join(lines)
