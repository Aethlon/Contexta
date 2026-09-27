"""Strictly typed decision models for Contexta Cortex.

Cortex acts as the decision and routing layer powered by JEV (TypeSafe System One).
Raw JEV responses are normalized into these immutable, validated models so that
vendor-specific payload shapes never leak into the rest of Contexta.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class CortexTelemetry(BaseModel):
    """Telemetry and operational metrics for a Cortex decision."""

    latency_ms: float = 0.0
    source: str = "jev"  # "jev" | "heuristic_fallback" | "disabled"
    jev_request_id: str | None = None
    error: str | None = None


class CortexWriteDecision(BaseModel):
    """Normalized decision produced by Cortex for an incoming observation."""

    should_store: bool = True
    store_probability: float = 1.0
    suggested_memory_type: str = "fact"
    importance_score: float = 0.5
    is_update: bool = False
    needs_temporal: bool = False
    needs_entity_rel: bool = False
    extraction_depth: str = "normal"
    derived_summary: str = ""
    telemetry: CortexTelemetry = Field(default_factory=CortexTelemetry)

    @classmethod
    def from_jev_response(
        cls,
        data: dict[str, Any] | None,
        telemetry: CortexTelemetry,
    ) -> CortexWriteDecision:
        """Parse and safely normalize a raw JEV response into a CortexWriteDecision.

        Handles missing answers, malformed answers, unexpected choices, and varied
        confidence/probability formats without failing.
        """
        if not data or not isinstance(data, dict):
            return cls(
                derived_summary="Fallback: Empty or malformed JEV response",
                telemetry=telemetry,
            )

        answers = data.get("answers")
        if not isinstance(answers, dict):
            return cls(
                derived_summary="Fallback: Missing answers object in JEV response",
                telemetry=telemetry,
            )

        # 1. should_store (noul / boolean probability)
        store_prob = _extract_noul(answers.get("should_store"), default=0.9)
        should_store = store_prob >= 0.5

        # 2. memory_type (choice)
        valid_types = {"preference", "fact", "decision", "goal", "event", "rule", "attribute"}
        raw_type = _extract_choice(answers.get("memory_type"))
        suggested_type = raw_type.lower() if raw_type and raw_type.lower() in valid_types else "fact"

        # 3. importance (score, typically on 1-10 scale)
        raw_importance = _extract_score(answers.get("importance"), default=5.0)
        # Normalize 1-10 scale down to 0.1 - 1.0, clamped between 0.0 and 1.0
        if raw_importance > 1.0:
            importance_score = max(0.0, min(1.0, round(raw_importance / 10.0, 2)))
        else:
            importance_score = max(0.0, min(1.0, round(raw_importance, 2)))

        # 4. is_update (noul)
        is_update_prob = _extract_noul(answers.get("is_update"), default=0.0)
        is_update = is_update_prob >= 0.5

        # 5. needs_temporal (noul)
        temporal_prob = _extract_noul(answers.get("needs_temporal"), default=0.0)
        needs_temporal = temporal_prob >= 0.5

        # 6. needs_entity_rel (noul)
        entity_prob = _extract_noul(answers.get("needs_entity_rel"), default=0.0)
        needs_entity_rel = entity_prob >= 0.5

        # 7. extraction_depth (choice: normal vs deep)
        raw_depth = _extract_choice(answers.get("extraction_depth"))
        extraction_depth = "deep" if raw_depth and raw_depth.lower() == "deep" else "normal"

        # Derive local human-readable summary (never asked to JEV)
        summary = (
            f"Cortex: store={should_store} (p={store_prob:.2f}), type={suggested_type}, "
            f"importance={importance_score:.2f}, update={is_update}, depth={extraction_depth}"
        )

        return cls(
            should_store=should_store,
            store_probability=round(store_prob, 3),
            suggested_memory_type=suggested_type,
            importance_score=importance_score,
            is_update=is_update,
            needs_temporal=needs_temporal,
            needs_entity_rel=needs_entity_rel,
            extraction_depth=extraction_depth,
            derived_summary=summary,
            telemetry=telemetry,
        )


class CortexReadDecision(BaseModel):
    """Normalized decision produced by Cortex for an incoming retrieval query."""

    strategy: str = "hybrid"  # "hybrid" | "semantic" | "exact" | "graph" | "temporal"
    requires_graph: bool = False
    requires_temporal_filter: bool = False
    priority_memory_type: str | None = None
    derived_summary: str = ""
    telemetry: CortexTelemetry = Field(default_factory=CortexTelemetry)

    @classmethod
    def from_jev_response(
        cls,
        data: dict[str, Any] | None,
        telemetry: CortexTelemetry,
    ) -> CortexReadDecision:
        """Parse and safely normalize a raw JEV response into a CortexReadDecision."""
        if not data or not isinstance(data, dict):
            return cls(
                derived_summary="Fallback: Empty or malformed JEV response",
                telemetry=telemetry,
            )

        answers = data.get("answers")
        if not isinstance(answers, dict):
            return cls(
                derived_summary="Fallback: Missing answers object in JEV response",
                telemetry=telemetry,
            )

        # 1. strategy (choice)
        valid_strategies = {"hybrid", "semantic", "exact", "graph", "temporal"}
        raw_strategy = _extract_choice(answers.get("retrieval_strategy"))
        strategy = raw_strategy.lower() if raw_strategy and raw_strategy.lower() in valid_strategies else "hybrid"

        # 2. requires_graph (noul)
        graph_prob = _extract_noul(answers.get("requires_graph"), default=0.0)
        requires_graph = graph_prob >= 0.5 or strategy == "graph"

        # 3. requires_temporal_filter (noul)
        temp_prob = _extract_noul(answers.get("requires_temporal_filter"), default=0.0)
        requires_temporal = temp_prob >= 0.5 or strategy == "temporal"

        # 4. priority_memory_type (choice)
        valid_mem_types = {"preference", "fact", "decision", "goal", "event", "rule"}
        raw_priority = _extract_choice(answers.get("priority_memory_type"))
        priority_type = (
            raw_priority.lower()
            if raw_priority and raw_priority.lower() in valid_mem_types
            else None
        )

        summary = (
            f"Cortex: strategy={strategy}, graph={requires_graph}, "
            f"temporal={requires_temporal}, priority_type={priority_type or 'all'}"
        )

        return cls(
            strategy=strategy,
            requires_graph=requires_graph,
            requires_temporal_filter=requires_temporal,
            priority_memory_type=priority_type,
            derived_summary=summary,
            telemetry=telemetry,
        )


# ── Internal Extraction Helpers ──────────────────────────────────────────

def _extract_noul(value: Any, default: float = 0.5) -> float:
    """Safely extract boolean probability from a noul answer."""
    if isinstance(value, dict):
        if "noul" in value and isinstance(value["noul"], (int, float)):
            return float(value["noul"])
        if "probability" in value and isinstance(value["probability"], (int, float)):
            return float(value["probability"])
        if "choice" in value:
            c = str(value["choice"]).lower()
            return 1.0 if c in ("yes", "true", "1") else 0.0
    elif isinstance(value, (int, float)):
        return float(value)
    elif isinstance(value, bool):
        return 1.0 if value else 0.0
    return default


def _extract_choice(value: Any) -> str | None:
    """Safely extract choice option string from a choice answer."""
    if isinstance(value, dict):
        if "choice" in value and isinstance(value["choice"], str):
            return value["choice"]
        if "selected" in value and isinstance(value["selected"], str):
            return value["selected"]
    elif isinstance(value, str):
        return value
    return None


def _extract_score(value: Any, default: float = 5.0) -> float:
    """Safely extract numerical score from a score answer."""
    if isinstance(value, dict):
        if "score" in value and isinstance(value["score"], (int, float)):
            return float(value["score"])
        if "value" in value and isinstance(value["value"], (int, float)):
            return float(value["value"])
    elif isinstance(value, (int, float)):
        return float(value)
    return default
