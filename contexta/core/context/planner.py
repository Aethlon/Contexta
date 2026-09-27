from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from contexta.core.schemas import TokenAllocation

try:
    from contexta.core.schemas import TokenAllocation
except NameError:
    @dataclass
    class TokenAllocation:
        total_budget: int
        allocations: dict[str, int]
        actual_usage: dict[str, int]

DEFAULT_WEIGHTS = {
    "projects": 0.35,
    "goals": 0.20,
    "facts": 0.15,
    "episodic": 0.15,
    "preferences": 0.10,
    "relationships": 0.05,
}


def _payload_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("evidence_id", "memory_id", "id"):
            value = payload.get(key)
            if value is not None:
                return str(value)
        return None
    for key in ("evidence_id", "memory_id", "id"):
        value = getattr(payload, key, None)
        if value is not None:
            return str(value)
    return None


@dataclass(frozen=True)
class ContextItem:
    category: str
    token_count: int
    relevance: float
    payload: object
    cluster_id: str | None = None
    is_summary: bool = False
    required: bool = False
    order: int = 0

    @property
    def evidence_id(self) -> str | None:
        return _payload_id(self.payload)

    @property
    def is_required(self) -> bool:
        return self.required


class ContextPlanner:
    def allocate(
        self,
        total_budget: int,
        *,
        custom_weights: dict[str, float] | None = None,
    ) -> TokenAllocation:
        weights = custom_weights or DEFAULT_WEIGHTS
        total_weight = sum(weights.values()) or 1.0
        allocations = {
            category: int(total_budget * weight / total_weight)
            for category, weight in weights.items()
        }
        remainder = total_budget - sum(allocations.values())
        for category in list(allocations)[:remainder]:
            allocations[category] += 1
        return TokenAllocation(total_budget=total_budget, allocations=allocations)

    def fill_budget(
        self,
        allocation: TokenAllocation,
        items: list[ContextItem],
        *,
        required_ids: Collection[str] | None = None,
        required: Collection[str] | None = None,
        minimum_evidence: int | None = None,
        preserve_order: bool = False,
    ) -> tuple[list[ContextItem], TokenAllocation]:
        required_values = {
            str(value.evidence_id if isinstance(value, ContextItem) else value)
            for value in [*(required_ids or ()), *(required or ())]
            if value is not None
        }
        order_map = {id(item): index for index, item in enumerate(items)}
        unique_items: list[ContextItem] = []
        seen_evidence: set[str] = set()
        required_evidence: set[str] = set()
        for item in items:
            identifier = item.evidence_id
            if item.required and identifier is not None:
                required_evidence.add(identifier)
            if identifier is not None and identifier in seen_evidence:
                continue
            if identifier is not None:
                seen_evidence.add(identifier)
            unique_items.append(item)

        def is_required(item: ContextItem) -> bool:
            return (
                item.required
                or item.evidence_id in required_values
                or item.evidence_id in required_evidence
            )

        required_items = [item for item in unique_items if is_required(item)]
        optional_items = [item for item in unique_items if not is_required(item)]
        ordered_optional = sorted(
            optional_items,
            key=lambda item: order_map[id(item)] if preserve_order else (-item.relevance, order_map[id(item)]),
        )
        minimum_count = max(0, int(minimum_evidence or 0))
        for item in ordered_optional:
            if len(required_items) >= minimum_count:
                break
            required_items.append(item)
        selected_optional = {id(item) for item in required_items}
        ordered_optional = [
            item for item in ordered_optional if id(item) not in selected_optional
        ]
        selected: list[ContextItem] = []
        selected_ids: set[int] = set()
        actual_usage = {category: 0 for category in allocation.allocations}

        def select(item: ContextItem) -> None:
            if id(item) in selected_ids:
                return
            selected.append(item)
            selected_ids.add(id(item))
            actual_usage[item.category] = actual_usage.get(item.category, 0) + max(0, item.token_count)

        for item in required_items:
            select(item)

        for category in allocation.allocations:
            for item in ordered_optional:
                if item.category != category or id(item) in selected_ids:
                    continue
                if actual_usage.get(category, 0) + item.token_count <= allocation.allocations[category]:
                    select(item)

        used_total = sum(actual_usage.values())
        unused = max(0, allocation.total_budget - used_total)
        for item in ordered_optional:
            if id(item) in selected_ids:
                continue
            if unused < item.token_count:
                continue
            select(item)
            unused -= item.token_count

        if preserve_order:
            selected.sort(key=lambda item: order_map[id(item)])
        else:
            selected.sort(key=lambda item: (-item.relevance, order_map[id(item)]))
        allocation.actual_usage = actual_usage
        return selected, allocation

    def _group_items(self, items: list[ContextItem]) -> dict[str, list[ContextItem]]:
        grouped: dict[str, list[ContextItem]] = {}
        for item in items:
            grouped.setdefault(item.category, []).append(item)
        return grouped


def build_context_items(
    values: list[Any],
    *,
    category_for: Any = None,
    required_ids: Collection[str] | None = None,
) -> list[ContextItem]:
    required = {str(value) for value in (required_ids or ())}
    items: list[ContextItem] = []
    for order, value in enumerate(values):
        payload = getattr(value, "memory", value)
        if isinstance(value, dict) and "memory" in value:
            payload = value["memory"]
        category = category_for(payload) if category_for is not None else "facts"
        content = getattr(payload, "content", None)
        if content is None and isinstance(payload, dict):
            content = payload.get("content", "")
        identifier = value.get("evidence_id") if isinstance(value, Mapping) else getattr(value, "evidence_id", None)
        if identifier is None and isinstance(value, Mapping):
            identifier = value.get("memory_id") or value.get("id")
        if identifier is None:
            identifier = _payload_id(payload)
        score = getattr(value, "score", None)
        if score is None and isinstance(value, dict):
            score = value.get("score", value.get("retrieval_score"))
        if score is None:
            score = getattr(payload, "importance", 0.0)
        try:
            relevance = float(score)
        except (TypeError, ValueError):
            relevance = 0.0
        items.append(
            ContextItem(
                category=category,
                token_count=max(1, len(str(content or "").split())),
                relevance=relevance,
                payload=payload,
                required=str(identifier) in required if identifier is not None else False,
                order=order,
            )
        )
    return items


__all__ = ["ContextItem", "ContextPlanner", "build_context_items"]
