"""Context assembly."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from contexta.core.context.context_package import ContextPackage, ContextPackageBuilder
from contexta.core.context.planner import ContextItem, ContextPlanner
from contexta.core.retrieval.query_understanding import QueryPlan, build_query_plan
from contexta.models.memory import MemoryRecord

if TYPE_CHECKING:
    from contexta.core.schemas import ContextRequest


@dataclass
class BuiltContext:
    user_profile: dict[str, Any] = field(default_factory=dict)
    rules: list[dict[str, Any]] = field(default_factory=list)
    active_projects: list[dict[str, Any]] = field(default_factory=list)
    preferences: list[dict[str, Any]] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    query_plan: QueryPlan | None = None
    evidence_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    answerability: bool = False
    table_rows: list[dict[str, Any]] = field(default_factory=list)
    ordered_items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.ordered_items


class ContextBuilder:
    """Assemble structured context from retrieved memories."""

    def __init__(self, planner: ContextPlanner | None = None) -> None:
        self._planner = planner or ContextPlanner()
        self._cache: dict[str, BuiltContext] = {}

    def build(
        self,
        request: ContextRequest,
        memories: Sequence[MemoryRecord | Any],
        *,
        cache_key: str | None = None,
        newest_memory_timestamp: str | None = None,
        preserve_input_order: bool | None = None,
        required_evidence_ids: Sequence[str] = (),
        query_plan: QueryPlan | None = None,
        query_text: str | None = None,
    ) -> BuiltContext:
        plan = query_plan or (build_query_plan(query_text) if query_text else None)
        values = list(memories)
        if preserve_input_order is None:
            preserve_input_order = plan is not None or any(
                self._has_memory_wrapper(value) for value in values
            )
        cache_signature = self._cache_signature(
            plan=plan,
            required_evidence_ids=required_evidence_ids,
            query_text=query_text,
        )
        if cache_key and cache_key in self._cache:
            cached = self._cache[cache_key]
            if (
                cached.metadata.get("newest_memory_timestamp") == newest_memory_timestamp
                and cached.metadata.get("cache_signature") == cache_signature
                and bool(preserve_input_order) == cached.metadata.get("preserve_input_order")
            ):
                return cached

        required_ids = {str(value) for value in required_evidence_ids if value is not None}
        if plan is not None:
            required_ids.update(str(value) for value in plan.required_evidence_ids if value is not None)
        unwrapped: list[tuple[Any, Any]] = [
            (self._memory_from_value(value), value) for value in values
        ]
        valid_values = [
            (memory, source)
            for memory, source in unwrapped
            if memory is not None
            and not self._field(memory, "is_archived", False)
            and self._field(memory, "valid_to") is None
        ]
        if plan is not None and plan.explicit_temporal_constraints:
            valid_values = [
                value
                for value in valid_values
                if self._matches_temporal_constraints(
                    value,
                    plan.explicit_temporal_constraints,
                )
            ]
        if not preserve_input_order:
            valid_values.sort(
                key=lambda pair: float(self._field(pair[0], "importance", 0.0) or 0.0),
                reverse=True,
            )
        unique_values = self._deduplicate_values(valid_values, required_ids=required_ids)
        coverage_limit = request.config.num_relevant_memories
        if plan is not None:
            coverage_limit = max(coverage_limit, plan.retrieval_limit_hint)
        valid_values = self._limit_with_required(
            unique_values,
            limit=coverage_limit,
            required_ids=required_ids,
            preserve_table_rows=plan is not None and plan.is_table,
        )

        context = BuiltContext(query_plan=plan)
        selected_values = valid_values
        if request.config.token_budget:
            allocation = self._planner.allocate(
                request.config.token_budget,
                custom_weights=request.config.custom_weights,
            )
            planner_items = [
                ContextItem(
                    category=self._category_for(memory),
                    token_count=self._estimate_memory_tokens(memory),
                    relevance=self._relevance_for(memory, source),
                    payload=memory,
                    required=(
                        self._value_is_required((memory, source), required_ids)
                        or (
                            plan is not None
                            and plan.is_table
                            and self._value_has_table_rows((memory, source))
                        )
                    ),
                    order=order,
                )
                for order, (memory, source) in enumerate(valid_values)
            ]
            selected_items, allocation = self._planner.fill_budget(
                allocation,
                planner_items,
                required_ids=required_ids,
                minimum_evidence=plan.required_evidence_count if plan is not None else None,
                preserve_order=preserve_input_order,
            )
            selected_payload_ids = {id(item.payload) for item in selected_items}
            if preserve_input_order:
                selected_values = [
                    value for value in valid_values if id(value[0]) in selected_payload_ids
                ]
            else:
                values_by_payload = {id(memory): (memory, source) for memory, source in valid_values}
                selected_values = [
                    values_by_payload[id(item.payload)]
                    for item in selected_items
                    if id(item.payload) in values_by_payload
                ]
            context.metadata["token_usage"] = allocation.actual_usage

        for order, (memory, source) in enumerate(selected_values, 1):
            retrieval_rank = self._field(source, "rank")
            if retrieval_rank is None:
                retrieval_rank = self._field(source, "retrieval_rank", order)
            retrieval_score = self._field(source, "score")
            if retrieval_score is None:
                retrieval_score = self._field(source, "retrieval_score")
            item = self._memory_payload(
                memory,
                source=source,
                retrieval_rank=int(retrieval_rank or order),
                retrieval_score=retrieval_score,
            )
            context.ordered_items.append(item)
            memory_type_value = self._field(memory, "memory_type", "")
            memory_type = str(getattr(memory_type_value, "value", memory_type_value) or "")
            tags = {str(tag) for tag in (self._field(memory, "tags", []) or [])}
            if memory_type == "profile" or tags.intersection({"profile", "identity", "onboarding"}):
                structured = self._field(memory, "structured_data")
                if isinstance(structured, Mapping):
                    for key, value in structured.items():
                        if value is not None:
                            context.user_profile[key] = value
                else:
                    context.preferences.append(item)
            if memory_type in {"procedural", "rule"}:
                context.rules.append(item)
            elif memory_type == "project":
                context.active_projects.append(item)
            elif memory_type == "preference":
                context.preferences.append(item)
            elif memory_type == "goal":
                context.goals.append(item)
            elif memory_type in {"event", "episodic"}:
                context.recent_events.append(item)
            elif memory_type != "profile":
                context.relevant_memories.append(item)

        if not preserve_input_order:
            context.recent_events.sort(
                key=lambda item: item.get("event_at") or item.get("observed_at") or "",
                reverse=True,
            )
        context.table_rows = self._structured_table_rows(context.ordered_items)
        context.evidence_ids = list(
            dict.fromkeys(
                str(item.get("evidence_id") or item.get("id"))
                for item in context.ordered_items
                if item.get("evidence_id") or item.get("id")
            )
        )
        context.source_ids = list(
            dict.fromkeys(
                source_id
                for item in context.ordered_items
                for source_id in item.get("source_ids", [])
            )
        )
        evidence_id_set = set(context.evidence_ids)
        minimum_evidence = plan.required_evidence_count if plan is not None else 1
        context.answerability = (
            len(evidence_id_set) >= minimum_evidence
            and required_ids.issubset(evidence_id_set)
            and self._plan_constraints_satisfied(context.ordered_items, plan)
        )
        context.metadata["newest_memory_timestamp"] = newest_memory_timestamp
        context.metadata["preserve_input_order"] = bool(preserve_input_order)
        context.metadata["cache_signature"] = cache_signature
        context.metadata["evidence_ids"] = context.evidence_ids
        context.metadata["source_ids"] = context.source_ids
        context.metadata["answerability"] = context.answerability
        context.metadata["retrieval_order_preserved"] = bool(preserve_input_order)
        if plan is not None:
            context.metadata["query_plan"] = plan.model_dump(mode="json")
            context.metadata["required_evidence_ids"] = sorted(required_ids)
            context.metadata["missing_evidence_ids"] = sorted(required_ids - evidence_id_set)
            context.metadata["required_evidence_retained"] = required_ids.issubset(evidence_id_set)
        if cache_key:
            self._cache[cache_key] = context
        return context

    def build_package(
        self,
        request: ContextRequest,
        memories: Sequence[MemoryRecord | Any],
        *,
        query: str | QueryPlan | None = None,
        query_plan: QueryPlan | None = None,
        required_evidence_ids: Sequence[str] = (),
        cache_key: str | None = None,
        newest_memory_timestamp: str | None = None,
    ) -> ContextPackage:
        plan = query_plan or (query if isinstance(query, QueryPlan) else build_query_plan(query or ""))
        built = self.build(
            request,
            memories,
            cache_key=cache_key,
            newest_memory_timestamp=newest_memory_timestamp,
            preserve_input_order=True,
            required_evidence_ids=required_evidence_ids,
            query_plan=plan,
        )
        return ContextPackageBuilder().build_from_context(
            query if isinstance(query, str) else plan.query_text,
            built,
            query_plan=plan,
            required_evidence_ids=required_evidence_ids,
        )

    def build_query_package(self, *args: Any, **kwargs: Any) -> ContextPackage:
        return self.build_package(*args, **kwargs)

    def build_context_package(self, *args: Any, **kwargs: Any) -> ContextPackage:
        return self.build_package(*args, **kwargs)

    def build_context(self, *args: Any, **kwargs: Any) -> BuiltContext:
        return self.build(*args, **kwargs)

    @staticmethod
    def _cache_signature(
        *,
        plan: QueryPlan | None,
        required_evidence_ids: Sequence[str],
        query_text: str | None,
    ) -> str:
        plan_value = plan.model_dump_json() if plan is not None else ""
        required_value = ",".join(sorted(str(value) for value in required_evidence_ids))
        return f"{query_text or ''}|{required_value}|{plan_value}"

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, Mapping):
            return value.get(name, default)
        return getattr(value, name, default)

    @classmethod
    def _has_memory_wrapper(cls, value: Any) -> bool:
        return (isinstance(value, Mapping) and "memory" in value) or hasattr(value, "memory")

    @classmethod
    def _memory_from_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping) and "memory" in value:
            return value["memory"]
        memory = getattr(value, "memory", None)
        return memory if memory is not None else value

    @classmethod
    def _value_id(cls, value: Any) -> str:
        for item in (value, cls._memory_from_value(value)):
            for name in ("evidence_id", "memory_id", "id"):
                candidate = cls._field(item, name)
                if candidate is not None:
                    return str(candidate)
        return ""

    @classmethod
    def _memory_id(cls, memory: Any) -> str:
        return cls._value_id(memory)

    @classmethod
    def _value_is_required(cls, value: tuple[Any, Any], required_ids: set[str]) -> bool:
        identifiers = {
            identifier
            for item in value
            for identifier in (cls._value_id(item),)
            if identifier
        }
        return bool(identifiers.intersection(required_ids))

    @classmethod
    def _value_has_table_rows(cls, value: tuple[Any, Any]) -> bool:
        for item in value:
            structured = cls._field(item, "structured_data")
            if cls._structured_table_rows([{"structured_data": structured}]):
                return True
            rows = cls._field(item, "table_rows")
            if isinstance(rows, list) and any(isinstance(row, Mapping) for row in rows):
                return True
        return False

    @classmethod
    def _deduplicate_values(
        cls,
        values: list[tuple[Any, Any]],
        *,
        required_ids: set[str],
    ) -> list[tuple[Any, Any]]:
        result: list[tuple[Any, Any]] = []
        seen: set[tuple[str, str]] = set()
        for memory, source in values:
            identifier = cls._value_id(source) or cls._value_id(memory)
            if identifier:
                key = ("id", identifier)
            else:
                normalized = re.sub(
                    r"\s+",
                    " ",
                    f"{cls._field(memory, 'title', '')}\n{cls._field(memory, 'content', '')}".casefold(),
                ).strip()
                key = ("content", f"{cls._field(memory, 'memory_type', '')}:{normalized}")
            if key in seen:
                continue
            seen.add(key)
            result.append((memory, source))
        return result

    @classmethod
    def _limit_with_required(
        cls,
        values: list[tuple[Any, Any]],
        *,
        limit: int,
        required_ids: set[str],
        preserve_table_rows: bool = False,
    ) -> list[tuple[Any, Any]]:
        def is_required(value: tuple[Any, Any]) -> bool:
            return (
                cls._value_is_required(value, required_ids)
                or (preserve_table_rows and cls._value_has_table_rows(value))
            )

        if not required_ids and not preserve_table_rows:
            return values[:limit]
        required_count = sum(is_required(value) for value in values)
        optional_limit = max(0, limit - required_count)
        selected: list[tuple[Any, Any]] = []
        optional_count = 0
        for value in values:
            if is_required(value):
                selected.append(value)
            elif optional_count < optional_limit:
                selected.append(value)
                optional_count += 1
        return selected

    @staticmethod
    def _estimate_memory_tokens(memory: Any) -> int:
        content = ContextBuilder._field(memory, "content", "")
        return max(1, len(str(content or "").split()))

    @classmethod
    def _relevance_for(cls, memory: Any, source: Any) -> float:
        value = cls._field(source, "score")
        if value is None:
            value = cls._field(source, "retrieval_score")
        if value is None:
            value = cls._field(memory, "importance", 0.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _all_items(context: BuiltContext) -> list[dict[str, Any]]:
        if context.ordered_items:
            return context.ordered_items
        return [
            *context.rules,
            *context.preferences,
            *context.active_projects,
            *context.goals,
            *context.recent_events,
            *context.relevant_memories,
        ]

    @staticmethod
    def _structured_table_rows(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in items:
            structured = item.get("structured_data")
            candidates: list[Any] = []
            if isinstance(structured, Mapping):
                table = structured.get("table")
                if isinstance(table, Mapping):
                    candidates.extend(
                        table.get("rows")
                        or table.get("data")
                        or table.get("records")
                        or []
                    )
                elif isinstance(table, list):
                    candidates.extend(table)
                tables = structured.get("tables")
                if isinstance(tables, list):
                    for nested in tables:
                        if not isinstance(nested, Mapping):
                            continue
                        nested_table = nested.get("table", nested)
                        if isinstance(nested_table, Mapping):
                            candidates.extend(
                                nested_table.get("rows")
                                or nested_table.get("data")
                                or nested_table.get("records")
                                or []
                            )
                for key in ("rows", "table_rows", "records", "items", "results"):
                    value = structured.get(key)
                    if isinstance(value, list):
                        candidates.extend(value)
            elif isinstance(structured, list):
                candidates.extend(structured)
            for row in candidates:
                if not isinstance(row, Mapping):
                    continue
                normalized = dict(row)
                if normalized not in rows:
                    rows.append(normalized)
        return rows

    @classmethod
    def _matches_temporal_constraints(
        cls,
        value: tuple[Any, Any],
        constraints: Sequence[Any],
    ) -> bool:
        if not constraints:
            return True
        memory, source = value
        event_value = cls._field(memory, "event_at")
        if isinstance(event_value, str):
            try:
                event_value = datetime.fromisoformat(event_value)
            except ValueError:
                event_value = None
        if isinstance(event_value, datetime):
            event_at = (
                event_value
                if event_value.tzinfo is not None
                else event_value.replace(tzinfo=UTC)
            )
        else:
            event_at = None
        searchable = " ".join(
            str(part)
            for part in (
                cls._field(source, "title"),
                cls._field(source, "content"),
                cls._field(memory, "title"),
                cls._field(memory, "content"),
                " ".join(str(item) for item in (cls._field(memory, "tags", []) or [])),
                cls._field(memory, "structured_data"),
            )
            if part
        ).casefold()
        for constraint in constraints:
            start = getattr(constraint, "start", None)
            end = getattr(constraint, "end", None)
            if start is not None and start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
            if end is not None and end.tzinfo is None:
                end = end.replace(tzinfo=UTC)
            if event_at is not None:
                if (start is not None and event_at < start) or (
                    end is not None and event_at >= end
                ):
                    return False
            elif str(getattr(constraint, "expression", "")).casefold() not in searchable:
                return False
        return True

    @staticmethod
    def _plan_constraints_satisfied(
        items: Sequence[Mapping[str, Any]],
        plan: QueryPlan | None,
    ) -> bool:
        if plan is None or not plan.explicit_constraints:
            return True
        for constraint in plan.temporal_constraints:
            if not constraint.explicit:
                continue
            matched = False
            for item in items:
                event_value = item.get("event_at")
                event_at = None
                if isinstance(event_value, datetime):
                    event_at = event_value
                elif isinstance(event_value, str):
                    try:
                        event_at = datetime.fromisoformat(event_value)
                    except ValueError:
                        event_at = None
                if event_at is not None:
                    if event_at.tzinfo is None:
                        event_at = event_at.replace(tzinfo=UTC)
                    start = constraint.start
                    end = constraint.end
                    if start is not None and start.tzinfo is None:
                        start = start.replace(tzinfo=UTC)
                    if end is not None and end.tzinfo is None:
                        end = end.replace(tzinfo=UTC)
                    if (start is None or event_at >= start) and (end is None or event_at < end):
                        matched = True
                        break
                if constraint.expression.casefold() in str(item.get("content") or "").casefold():
                    matched = True
                    break
            if not matched:
                return False
        if plan.requires_entity_coverage:
            searchable = " ".join(
                str(item.get(key) or "")
                for item in items
                for key in ("title", "content", "structured_data", "tags")
            ).casefold()
            if any(
                re.search(rf"(?<!\w){re.escape(entity.casefold())}(?!\w)", searchable) is None
                for entity in plan.entities
            ):
                return False
        return True

    def _memory_payload(
        self,
        memory: Any,
        *,
        source: Any = None,
        retrieval_rank: int | None = None,
        retrieval_score: float | None = None,
    ) -> dict[str, Any]:
        event_at = self._field(memory, "event_at")
        observed_at = self._field(memory, "observed_at")
        structured_data = self._field(memory, "structured_data")
        if structured_data is None:
            structured_data = self._field(source, "structured_data")
        structured_copy = dict(structured_data) if isinstance(structured_data, Mapping) else structured_data
        temporal_metadata: dict[str, Any] = {}
        if isinstance(structured_data, Mapping) and isinstance(structured_data.get("temporal"), Mapping):
            temporal_metadata.update(structured_data["temporal"])
        for name in (
            "event_at",
            "observed_at",
            "temporal_precision",
            "temporal_basis",
            "fact_key",
            "valid_from",
            "valid_to",
        ):
            value = self._field(memory, name)
            if value is not None:
                temporal_metadata[name] = value
        source_ids = self._source_ids(memory, source)
        identifier = self._value_id(source) or self._value_id(memory)
        memory_type = self._field(memory, "memory_type")
        memory_type = getattr(memory_type, "value", memory_type)
        payload = {
            "id": identifier,
            "evidence_id": identifier,
            "type": memory_type,
            "memory_type": memory_type,
            "title": self._field(memory, "title"),
            "content": self._field(memory, "content", ""),
            "importance": self._field(memory, "importance", 0.0),
            "confidence": self._field(memory, "confidence", 0.0),
            "utility_score": self._field(memory, "utility_score", 0.0),
            "tags": self._field(memory, "tags", []) or [],
            "structured_data": structured_copy,
            "event_at": event_at.isoformat() if isinstance(event_at, datetime) else event_at,
            "observed_at": observed_at.isoformat() if isinstance(observed_at, datetime) else observed_at,
            "temporal": temporal_metadata,
            "temporal_metadata": temporal_metadata,
            "temporal_precision": self._field(memory, "temporal_precision"),
            "temporal_basis": self._field(memory, "temporal_basis"),
            "source_id": self._field(memory, "source_id") or (source_ids[0] if source_ids else None),
            "source_message_id": self._field(memory, "source_message_id"),
            "source_ids": source_ids,
            "fact_key": self._field(memory, "fact_key"),
            "lineage_id": self._field(memory, "lineage_id"),
            "retrieval_rank": retrieval_rank,
            "retrieval_score": retrieval_score,
            "score": retrieval_score,
        }
        return payload

    @staticmethod
    def _source_ids(memory: Any, source: Any = None) -> list[str]:
        values: list[Any] = []
        for item in (memory, source):
            if item is None:
                continue
            for name in ("source_id", "source_message_id", "observation_id", "source_ids"):
                candidate = ContextBuilder._field(item, name)
                if isinstance(candidate, (list, tuple, set)):
                    values.extend(candidate)
                elif candidate is not None:
                    values.append(candidate)
            structured = ContextBuilder._field(item, "structured_data")
            if isinstance(structured, Mapping):
                for name in ("source_id", "source_message_id", "observation_id", "source_ids"):
                    candidate = structured.get(name)
                    if isinstance(candidate, (list, tuple, set)):
                        values.extend(candidate)
                    elif candidate is not None:
                        values.append(candidate)
        return list(dict.fromkeys(str(value) for value in values if value is not None and str(value)))

    def _category_for(self, memory: Any) -> str:
        memory_type = self._field(memory, "memory_type", "")
        memory_type = str(getattr(memory_type, "value", memory_type) or "")
        return {
            "project": "projects",
            "goal": "goals",
            "preference": "preferences",
            "relationship": "relationships",
            "event": "episodic",
            "episodic": "episodic",
            "rule": "facts",
            "procedural": "facts",
        }.get(memory_type, "facts")

    @staticmethod
    def _prompt_content(item: dict[str, Any]) -> str:
        event_at = item.get("event_at")
        if event_at:
            return f"[Event date: {str(event_at)[:10]}] {item['content']}"
        return str(item["content"])

    def to_system_prompt(self, context: BuiltContext, *, format: str = "markdown") -> str:
        if format.lower() == "xml":
            return self.to_xml(context)
        sections: list[str] = []
        if context.rules:
            rules_block = ["## Operating Rules & Behavioral Directives"]
            for rule in context.rules:
                rules_block.append(f"- **{rule['title']}**: {self._prompt_content(rule)}")
            sections.append("\n".join(rules_block))
        if context.user_profile or context.preferences:
            pref_block = ["## User Profile & Preferences (The Soul)"]
            if context.user_profile:
                pref_block.append("### Core Identity")
                for key, value in context.user_profile.items():
                    key_fmt = str(key).replace("_", " ").title()
                    pref_block.append(f"- **{key_fmt}**: {value}")
            if context.preferences:
                pref_block.append("### Preferences & Traits")
                for preference in context.preferences:
                    pref_block.append(f"- {self._prompt_content(preference)}")
            sections.append("\n".join(pref_block))
        if context.active_projects or context.goals:
            project_block = ["## Active Projects & Goals"]
            for project in context.active_projects:
                project_block.append(f"- **Project: {project['title']}**: {self._prompt_content(project)}")
            for goal in context.goals:
                goal_block = f"- **Goal: {goal['title']}**: {self._prompt_content(goal)}"
                project_block.append(goal_block)
            sections.append("\n".join(project_block))
        if context.recent_events:
            event_block = ["## Recent Interaction History & Events"]
            for event in context.recent_events:
                event_block.append(f"- {self._prompt_content(event)}")
            sections.append("\n".join(event_block))
        if context.relevant_memories:
            fact_block = ["## Verified Knowledge & Facts"]
            for memory in context.relevant_memories:
                fact_block.append(f"- {self._prompt_content(memory)}")
            sections.append("\n".join(fact_block))
        return "\n\n".join(sections)

    def to_xml(self, context: BuiltContext) -> str:
        xml_lines: list[str] = ["<agent_context>"]
        if context.rules:
            xml_lines.append("  <operating_rules>")
            for rule in context.rules:
                xml_lines.append(f"    <rule title=\"{rule['title']}\">{self._prompt_content(rule)}</rule>")
            xml_lines.append("  </operating_rules>")
        if context.user_profile or context.preferences:
            xml_lines.append("  <user_profile>")
            if context.user_profile:
                xml_lines.append("    <core_identity>")
                for key, value in context.user_profile.items():
                    xml_lines.append(f"      <{key}>{value}</{key}>")
                xml_lines.append("    </core_identity>")
            if context.preferences:
                xml_lines.append("      <user_preferences>")
                for preference in context.preferences:
                    xml_lines.append(f"        <preference>{self._prompt_content(preference)}</preference>")
                xml_lines.append("      </user_preferences>")
            xml_lines.append("  </user_profile>")
        if context.active_projects or context.goals:
            xml_lines.append("  <active_projects_and_goals>")
            for project in context.active_projects:
                xml_lines.append(f"    <project title=\"{project['title']}\">{self._prompt_content(project)}</project>")
            for goal in context.goals:
                xml_lines.append(f"    <goal title=\"{goal['title']}\">{self._prompt_content(goal)}</goal>")
            xml_lines.append("  </active_projects_and_goals>")
        if context.recent_events:
            xml_lines.append("  <recent_history>")
            for event in context.recent_events:
                xml_lines.append(f"    <event>{self._prompt_content(event)}</event>")
            xml_lines.append("  </recent_history>")
        if context.relevant_memories:
            xml_lines.append("  <knowledge_facts>")
            for memory in context.relevant_memories:
                xml_lines.append(f"    <fact>{self._prompt_content(memory)}</fact>")
            xml_lines.append("  </knowledge_facts>")
        xml_lines.append("</agent_context>")
        return "\n".join(xml_lines)


__all__ = ["BuiltContext", "ContextBuilder"]
