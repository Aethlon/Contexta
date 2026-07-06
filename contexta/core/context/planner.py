"""Context token planning."""

from __future__ import annotations

from dataclasses import dataclass

from contexta.core.schemas import TokenAllocation


DEFAULT_WEIGHTS = {
    "projects": 0.35,
    "goals": 0.20,
    "facts": 0.15,
    "episodic": 0.15,
    "preferences": 0.10,
    "relationships": 0.05,
}


@dataclass(frozen=True)
class ContextItem:
    category: str
    token_count: int
    relevance: float
    payload: object
    cluster_id: str | None = None
    is_summary: bool = False


class ContextPlanner:
    """Allocate token budget and select highest-relevance context items."""

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
    ) -> tuple[list[ContextItem], TokenAllocation]:
        selected: list[ContextItem] = []
        actual_usage = {category: 0 for category in allocation.allocations}
        grouped = self._group_items(items)

        for category, budget in allocation.allocations.items():
            for item in sorted(grouped.get(category, []), key=lambda value: value.relevance, reverse=True):
                if actual_usage[category] + item.token_count > budget:
                    continue
                selected.append(item)
                actual_usage[category] += item.token_count

        unused = allocation.total_budget - sum(actual_usage.values())
        if unused > 0:
            remaining = sorted(
                [item for item in items if item not in selected],
                key=lambda value: value.relevance,
                reverse=True,
            )
            for item in remaining:
                if unused < item.token_count:
                    continue
                selected.append(item)
                actual_usage[item.category] = actual_usage.get(item.category, 0) + item.token_count
                unused -= item.token_count

        allocation.actual_usage = actual_usage
        return selected, allocation

    def _group_items(self, items: list[ContextItem]) -> dict[str, list[ContextItem]]:
        grouped: dict[str, list[ContextItem]] = {}
        for item in items:
            grouped.setdefault(item.category, []).append(item)
        return grouped
