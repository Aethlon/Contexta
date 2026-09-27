from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contexta.core.retrieval.query_understanding import (
    QueryPlan,
    TemporalConstraint,
    build_query_plan,
)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, UUID, int)):
        return [str(value)]
    return [str(item) for item in value if item is not None]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    evidence_id: str = ""
    id: str | None = None
    memory_id: str | None = None
    source_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    title: str | None = None
    content: str = ""
    memory_type: str | None = None
    source_type: str | None = None
    score: float = 0.0
    confidence: float = 0.0
    rank: int = Field(default=0, ge=0)
    structured_data: Any = None
    temporal_metadata: dict[str, Any] = Field(default_factory=dict)
    constraints_satisfied: list[str] = Field(default_factory=list)
    temporal_constraints_satisfied: list[str] = Field(default_factory=list)
    retrieval_score: float | None = None

    @field_validator("evidence_id", "id", "memory_id", "source_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: Any) -> str | None:
        return str(value) if value is not None else None

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_source_ids(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="after")
    def synchronize_ids(self) -> Evidence:
        if not self.evidence_id and self.id:
            self.evidence_id = self.id
        if not self.id:
            self.id = self.evidence_id or None
        if not self.memory_id and self.evidence_id:
            self.memory_id = self.evidence_id
        if self.source_id and self.source_id not in self.source_ids:
            self.source_ids.insert(0, self.source_id)
        self.source_ids = list(dict.fromkeys(str(item) for item in self.source_ids if item is not None and str(item)))
        self.constraints_satisfied = list(dict.fromkeys(str(item) for item in self.constraints_satisfied if item))
        self.temporal_constraints_satisfied = list(
            dict.fromkeys(str(item) for item in self.temporal_constraints_satisfied if item)
        )
        return self

    @property
    def temporal(self) -> dict[str, Any]:
        return self.temporal_metadata

    @property
    def evidence_confidence(self) -> float:
        return self.confidence


class StructuredTable(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_rows(self) -> StructuredTable:
        self.columns = [str(column) for column in self.columns]
        self.rows = [dict(row) for row in self.rows]
        return self


class EvidenceCoverage(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    required_evidence_ids: list[str] = Field(default_factory=list)
    covered_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence_ids: list[str] = Field(default_factory=list)
    required_entities: list[str] = Field(default_factory=list)
    covered_entities: list[str] = Field(default_factory=list)
    missing_entities: list[str] = Field(default_factory=list)
    required_constraints: list[str] = Field(default_factory=list)
    covered_constraints: list[str] = Field(default_factory=list)
    missing_constraints: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "required_evidence_ids",
        "covered_evidence_ids",
        "missing_evidence_ids",
        "required_entities",
        "covered_entities",
        "missing_entities",
        "required_constraints",
        "covered_constraints",
        "missing_constraints",
        mode="before",
    )
    @classmethod
    def normalize_values(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="after")
    def normalize_ids(self) -> EvidenceCoverage:
        for name in (
            "required_evidence_ids",
            "covered_evidence_ids",
            "missing_evidence_ids",
            "required_entities",
            "covered_entities",
            "missing_entities",
            "required_constraints",
            "covered_constraints",
            "missing_constraints",
        ):
            values = getattr(self, name)
            setattr(self, name, list(dict.fromkeys(str(item) for item in values if item)))
        return self


class ContextPackage(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    query: str = ""
    query_plan: QueryPlan | None = None
    intent: str = "fact"
    answer_shape: str = "text"
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    answerable: bool = False
    answerability: bool = False
    answerability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_coverage: EvidenceCoverage = Field(default_factory=EvidenceCoverage)
    table: StructuredTable | None = None
    table_rows: list[dict[str, Any]] = Field(default_factory=list)
    structured_data: Any = None
    temporal_metadata: dict[str, Any] = Field(default_factory=dict)
    required_evidence_ids: list[str] = Field(default_factory=list)
    covered_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence_ids: list[str] = Field(default_factory=list)
    answer_value: int | str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "evidence_ids",
        "source_ids",
        "required_evidence_ids",
        "covered_evidence_ids",
        "missing_evidence_ids",
        mode="before",
    )
    @classmethod
    def normalize_values(cls, value: Any) -> list[str]:
        return _string_list(value)

    @model_validator(mode="after")
    def synchronize_contract(self) -> ContextPackage:
        self.intent = self.intent.value if hasattr(self.intent, "value") else str(self.intent)
        self.answer_shape = self.answer_shape.value if hasattr(self.answer_shape, "value") else str(self.answer_shape)
        if self.query_plan is not None:
            if not self.query:
                self.query = self.query_plan.query_text
            if self.intent == "fact" and self.query_plan.intent.value != "fact":
                self.intent = self.query_plan.intent.value
            if self.answer_shape == "text" and self.query_plan.answer_shape.value != "text":
                self.answer_shape = self.query_plan.answer_shape.value
        if not self.evidence_ids:
            self.evidence_ids = [item.evidence_id for item in self.evidence if item.evidence_id]
        if not self.source_ids:
            self.source_ids = list(
                dict.fromkeys(source_id for item in self.evidence for source_id in item.source_ids)
            )
        if not self.required_evidence_ids:
            self.required_evidence_ids = list(self.evidence_coverage.required_evidence_ids)
        if not self.covered_evidence_ids:
            self.covered_evidence_ids = list(self.evidence_coverage.covered_evidence_ids)
        if not self.missing_evidence_ids:
            self.missing_evidence_ids = list(self.evidence_coverage.missing_evidence_ids)
        if self.table is None and self.table_rows:
            self.table = StructuredTable(
                columns=_table_columns(self.table_rows),
                rows=self.table_rows,
            )
        if self.table is not None and not self.table_rows:
            self.table_rows = [dict(row) for row in self.table.rows]
        if not self.answerability and self.answerable:
            self.answerability = True
        if self.answerability and not self.answerable:
            self.answerable = True
        if not self.answerability_score:
            self.answerability_score = self.evidence_coverage.score
        if not self.confidence and self.evidence:
            self.confidence = sum(item.confidence for item in self.evidence) / len(self.evidence)
        if self.structured_data is None and self.evidence:
            self.structured_data = {
                item.evidence_id: item.structured_data
                for item in self.evidence
                if item.structured_data is not None
            } or None
        return self

    @property
    def is_answerable(self) -> bool:
        return self.answerable and self.answerability

    @property
    def coverage(self) -> EvidenceCoverage:
        return self.evidence_coverage

    @property
    def structured_table(self) -> StructuredTable | None:
        return self.table

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    @property
    def confidence_score(self) -> float:
        return self.confidence

    @classmethod
    def from_results(
        cls,
        query: str | QueryPlan,
        results: Sequence[Any] = (),
        *,
        query_plan: QueryPlan | None = None,
        required_evidence_ids: Sequence[str] = (),
        token_budget: int | None = None,
        context: Any = None,
    ) -> ContextPackage:
        return build_context_package(
            query,
            results,
            query_plan=query_plan,
            required_evidence_ids=required_evidence_ids,
            token_budget=token_budget,
            context=context,
        )

    @classmethod
    def from_context(
        cls,
        query: str | QueryPlan,
        context: Any,
        *,
        query_plan: QueryPlan | None = None,
        required_evidence_ids: Sequence[str] = (),
        token_budget: int | None = None,
    ) -> ContextPackage:
        return build_context_package(
            query,
            query_plan=query_plan,
            required_evidence_ids=required_evidence_ids,
            token_budget=token_budget,
            context=context,
        )


ContextEvidence = Evidence
ContextTable = StructuredTable


def _safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _id_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        for key in ("evidence_id", "memory_id", "id"):
            candidate = _id_text(value.get(key))
            if candidate:
                return candidate
        if "memory" in value:
            return _id_text(value.get("memory"))
        return None
    for key in ("evidence_id", "memory_id", "id"):
        candidate = _field(value, key)
        if candidate is not None:
            return _id_text(candidate)
    memory = _field(value, "memory")
    if memory is not None and memory is not value:
        return _id_text(memory)
    return None


def _memory_from_result(value: Any) -> Any:
    if isinstance(value, Mapping) and "memory" in value:
        return value["memory"]
    memory = _field(value, "memory")
    if memory is not None and memory is not value:
        return memory
    return value


def _score_from_result(value: Any) -> float:
    score = _field(value, "score")
    if score is None:
        score = _field(value, "retrieval_score")
    if score is None:
        score = _field(_memory_from_result(value), "importance", 0.0)
    try:
        return max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        return 0.0


def _confidence_from_result(value: Any) -> float:
    confidence = _field(value, "confidence")
    if confidence is None:
        confidence = _field(_memory_from_result(value), "confidence")
    if confidence is None:
        return _score_from_result(value)
    try:
        return max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        return 0.0


def _source_ids(value: Any) -> list[str]:
    memory = _memory_from_result(value)
    values: list[Any] = []
    for item in (value, memory):
        for name in ("source_id", "source_message_id", "observation_id", "source_ids"):
            candidate = _field(item, name)
            if isinstance(candidate, (list, tuple, set)):
                values.extend(candidate)
            elif candidate is not None:
                values.append(candidate)
        structured = _field(item, "structured_data")
        if isinstance(structured, Mapping):
            for name in ("source_id", "source_message_id", "observation_id", "source_ids"):
                candidate = structured.get(name)
                if isinstance(candidate, (list, tuple, set)):
                    values.extend(candidate)
                elif candidate is not None:
                    values.append(candidate)
    result: list[str] = []
    for item in values:
        text = _id_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _temporal_metadata(value: Any) -> dict[str, Any]:
    memory = _memory_from_result(value)
    metadata: dict[str, Any] = {}
    for item in (value, memory):
        structured = _field(item, "structured_data")
        if isinstance(structured, Mapping):
            temporal = structured.get("temporal")
            if isinstance(temporal, Mapping):
                metadata.update(temporal)
        for name in ("temporal", "temporal_metadata"):
            candidate = _field(item, name)
            if isinstance(candidate, Mapping):
                metadata.update(candidate)
    for name in (
        "event_at",
        "observed_at",
        "temporal_precision",
        "temporal_basis",
        "fact_key",
        "valid_from",
        "valid_to",
    ):
        candidate = _field(memory, name)
        if candidate is None:
            candidate = _field(value, name)
        if candidate is not None:
            metadata[name] = _safe_value(candidate)
    return {str(key): _safe_value(item) for key, item in metadata.items()}


def _temporal_value(value: Any, *names: str) -> datetime | None:
    metadata = _temporal_metadata(value)
    for name in names:
        candidate = metadata.get(name)
        if isinstance(candidate, datetime):
            return candidate if candidate.tzinfo else candidate.replace(tzinfo=UTC)
        if isinstance(candidate, str):
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _matches_temporal_constraint(value: Any, constraint: Any) -> bool:
    if not getattr(constraint, "explicit", False):
        return True
    event_at = _temporal_value(value, "event_at")
    start = getattr(constraint, "start", None)
    end = getattr(constraint, "end", None)
    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if event_at is not None:
        if start is not None and event_at < start:
            return False
        return not (end is not None and event_at >= end)
    if start is None and end is None:
        return True
    memory = _memory_from_result(value)
    searchable = " ".join(
        str(part)
        for part in (
            _field(value, "title"),
            _field(value, "content"),
            _field(memory, "title"),
            _field(memory, "content"),
            " ".join(str(item) for item in (_field(memory, "tags", []) or [])),
            _field(memory, "structured_data"),
        )
        if part
    ).casefold()
    return str(getattr(constraint, "expression", "")).casefold() in searchable


def _mentions(value: Any, entity: str) -> bool:
    memory = _memory_from_result(value)
    parts = [
        _field(value, "title"),
        _field(value, "content"),
        _field(memory, "title"),
        _field(memory, "content"),
        " ".join(str(item) for item in (_field(memory, "tags", []) or [])),
        " ".join(str(item) for item in (_field(memory, "entities", []) or [])),
        _field(memory, "structured_data"),
    ]
    searchable = " ".join(str(part) for part in parts if part).casefold()
    entity_text = " ".join(str(entity).strip().split()).casefold()
    if not entity_text:
        return False
    return re.search(rf"(?<!\w){re.escape(entity_text)}(?!\w)", searchable) is not None


def _rows_from_structured(structured: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if isinstance(structured, list):
        return [], [dict(row) for row in structured if isinstance(row, Mapping)]
    if not isinstance(structured, Mapping):
        return [], []

    columns: list[str] = []
    rows: list[dict[str, Any]] = []

    def add_column(value: Any) -> None:
        if isinstance(value, Mapping):
            value = value.get("name", value.get("id"))
        if value is None:
            return
        column = str(value)
        if column and column not in columns:
            columns.append(column)

    def add_rows(value: Any) -> None:
        if not isinstance(value, list):
            return
        for row in value:
            if not isinstance(row, Mapping):
                continue
            normalized = dict(row)
            if normalized in rows:
                continue
            rows.append(normalized)
            for key in normalized:
                add_column(key)

    def add_table(value: Any) -> None:
        if isinstance(value, Mapping):
            raw_columns = value.get("columns")
            if not isinstance(raw_columns, list):
                raw_columns = value.get("headers")
            if isinstance(raw_columns, list):
                for column in raw_columns:
                    add_column(column)
            raw_rows = value.get("rows")
            if not isinstance(raw_rows, list):
                raw_rows = value.get("data")
            if not isinstance(raw_rows, list):
                raw_rows = value.get("records")
            add_rows(raw_rows)
            nested = value.get("table")
            if isinstance(nested, (Mapping, list)):
                add_table(nested)
            nested_tables = value.get("tables")
            if isinstance(nested_tables, list):
                for nested_table in nested_tables:
                    add_table(nested_table)
        elif isinstance(value, list):
            table_keys = {"table", "tables", "rows", "data", "records"}
            if any(
                isinstance(item, Mapping) and table_keys.intersection(item)
                for item in value
            ):
                for item in value:
                    add_table(item)
            else:
                add_rows(value)

    add_table(structured.get("table"))
    tables = structured.get("tables")
    if isinstance(tables, list):
        for table in tables:
            add_table(table)
    for key in ("rows", "table_rows", "records", "items", "results"):
        add_rows(structured.get(key))
    return columns, rows


def _has_structured_rows(value: Any) -> bool:
    memory = _memory_from_result(value)
    for item in (value, memory):
        structured = _field(item, "structured_data")
        if _rows_from_structured(structured)[1]:
            return True
        rows = _field(item, "table_rows")
        if isinstance(rows, list) and any(isinstance(row, Mapping) for row in rows):
            return True
    return False


def _table_columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _table_rows(evidence: Sequence[Evidence]) -> tuple[list[str], list[dict[str, Any]]]:
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    for item in evidence:
        item_columns, item_rows = _rows_from_structured(item.structured_data)
        for column in item_columns:
            if column not in columns:
                columns.append(column)
        for row in item_rows:
            normalized = {str(key): _safe_value(value) for key, value in row.items()}
            rows.append(normalized)
            for key in normalized:
                if key not in columns:
                    columns.append(key)
    if rows:
        return columns, rows
    rows = [
        {
            "evidence_id": item.evidence_id,
            "title": item.title,
            "content": item.content,
            "memory_type": item.memory_type,
            "event_at": item.temporal_metadata.get("event_at"),
            "source_ids": list(item.source_ids),
        }
        for item in evidence
    ]
    return _table_columns(rows), rows


def _context_items(context: Any) -> list[Any]:
    if context is None:
        return []
    for name in ("ordered_items", "retrieval_items", "evidence"):
        candidate = _field(context, name)
        if isinstance(candidate, list) and candidate:
            return list(candidate)
    keys = (
        "rules",
        "preferences",
        "active_projects",
        "goals",
        "recent_events",
        "relevant_memories",
    )
    values: list[Any] = []
    for key in keys:
        candidate = _field(context, key)
        if isinstance(candidate, list):
            values.extend(candidate)
    return values


def _context_table_rows(context: Any) -> list[dict[str, Any]]:
    if context is None:
        return []
    candidate = _field(context, "table_rows")
    if isinstance(candidate, list):
        return [dict(row) for row in candidate if isinstance(row, Mapping)]
    table = _field(context, "table")
    if isinstance(table, Mapping):
        return [dict(row) for row in table.get("rows", []) if isinstance(row, Mapping)]
    rows = _field(table, "rows")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _required_ids(values: Sequence[Any]) -> set[str]:
    return {value for item in values if (value := _id_text(item))}


def _estimate_tokens(value: Any) -> int:
    content = _field(_memory_from_result(value), "content", "")
    if content is None:
        content = _field(value, "content", "")
    return max(1, len(str(content or "").split()))


def _select_for_budget(
    values: Sequence[Any],
    *,
    token_budget: int | None,
    required_ids: set[str],
    minimum_evidence: int | None = None,
    preserve_structured_rows: bool = False,
) -> list[Any]:
    if not token_budget or token_budget <= 0:
        return list(values)
    selected_indices: set[int] = set()
    used = 0
    for index, value in enumerate(values):
        identifier = _id_text(value)
        if (
            (identifier and identifier in required_ids)
            or (preserve_structured_rows and _has_structured_rows(value))
        ):
            selected_indices.add(index)
            used += _estimate_tokens(value)
    minimum_count = max(0, int(minimum_evidence or 0))
    for index, value in enumerate(values):
        if len(selected_indices) >= minimum_count:
            break
        if index in selected_indices:
            continue
        selected_indices.add(index)
        used += _estimate_tokens(value)
    for index, value in enumerate(values):
        if index in selected_indices:
            continue
        tokens = _estimate_tokens(value)
        if used + tokens <= token_budget:
            selected_indices.add(index)
            used += tokens
    return [value for index, value in enumerate(values) if index in selected_indices]


def _plan_constraints(plan: QueryPlan) -> list[TemporalConstraint]:
    return [item for item in plan.temporal_constraints if item.explicit]


def _temporal_constraints_for(value: Any, constraints: Sequence[TemporalConstraint]) -> list[str]:
    return [
        constraint.expression
        for constraint in constraints
        if _matches_temporal_constraint(value, constraint)
    ]


class ContextPackageBuilder:
    def build(
        self,
        query: str | QueryPlan,
        results: Sequence[Any] = (),
        *,
        query_plan: QueryPlan | None = None,
        required_evidence_ids: Sequence[str] = (),
        token_budget: int | None = None,
        context: Any = None,
    ) -> ContextPackage:
        plan = query_plan or (query if isinstance(query, QueryPlan) else build_query_plan(query))
        query_text = plan.query_text
        source_values = _context_items(context) if context is not None else list(results)
        if context is not None and not source_values:
            source_values = list(results)
        required_ids = _required_ids(required_evidence_ids) | set(plan.required_evidence_ids)
        constraints = _plan_constraints(plan)
        if constraints:
            source_values = [
                value
                for value in source_values
                if all(
                    _matches_temporal_constraint(value, constraint)
                    for constraint in constraints
                )
            ]
        source_values = _select_for_budget(
            source_values,
            token_budget=token_budget,
            required_ids=required_ids,
            minimum_evidence=plan.required_evidence_count,
            preserve_structured_rows=plan.is_table,
        )
        evidence: list[Evidence] = []
        seen_ids: set[str] = set()
        for rank, value in enumerate(source_values, 1):
            if isinstance(value, Evidence):
                item = value.model_copy(
                    update={
                        "rank": value.rank or rank,
                        "constraints_satisfied": list(
                            dict.fromkeys(
                                [
                                    *value.constraints_satisfied,
                                    *_temporal_constraints_for(value, constraints),
                                    *[
                                        entity
                                        for entity in plan.entities
                                        if _mentions(value, entity)
                                    ],
                                ]
                            )
                        ),
                        "temporal_constraints_satisfied": list(
                            dict.fromkeys(
                                [
                                    *value.temporal_constraints_satisfied,
                                    *_temporal_constraints_for(value, constraints),
                                ]
                            )
                        ),
                    }
                )
                identifier = item.evidence_id or _id_text(value)
                if not identifier or identifier in seen_ids:
                    continue
                item.evidence_id = identifier
                seen_ids.add(identifier)
                evidence.append(item)
                continue
            memory = _memory_from_result(value)
            if memory is None:
                continue
            identifier = _id_text(value) or _id_text(memory)
            if not identifier or identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            structured = _field(value, "structured_data")
            if structured is None:
                structured = _field(memory, "structured_data")
            title = _field(value, "title") or _field(memory, "title")
            content = _field(value, "content")
            if content is None:
                content = _field(memory, "content", "")
            source_ids = _source_ids(value)
            temporal_satisfied = _temporal_constraints_for(value, constraints)
            entity_satisfied = [entity for entity in plan.entities if _mentions(value, entity)]
            evidence.append(
                Evidence(
                    evidence_id=identifier,
                    memory_id=_id_text(memory) or identifier,
                    source_id=source_ids[0] if source_ids else None,
                    source_ids=source_ids,
                    title=str(title) if title is not None else None,
                    content=str(content or ""),
                    memory_type=_enum_text(_field(memory, "memory_type")) or None,
                    source_type=_enum_text(_field(memory, "source_type")) or None,
                    score=_score_from_result(value),
                    confidence=_confidence_from_result(value),
                    rank=rank,
                    structured_data=_safe_value(structured),
                    temporal_metadata=_temporal_metadata(value),
                    constraints_satisfied=list(dict.fromkeys([*temporal_satisfied, *entity_satisfied])),
                    temporal_constraints_satisfied=temporal_satisfied,
                    retrieval_score=_field(value, "retrieval_score"),
                )
            )
        covered_ids = {item.evidence_id for item in evidence}
        required_entities = [
            entity for entity in plan.entities if plan.requires_entity_coverage
        ]
        covered_entities = [
            entity for entity in required_entities if any(_mentions(item, entity) for item in evidence)
        ]
        missing_entities = [entity for entity in required_entities if entity not in covered_entities]
        required_constraint_values = list(plan.explicit_constraints)
        covered_constraints = [
            expression
            for expression in required_constraint_values
            if any(
                expression.casefold()
                in {value.casefold() for value in item.temporal_constraints_satisfied}
                for item in evidence
            )
        ]
        missing_constraints = [
            expression for expression in required_constraint_values if expression not in covered_constraints
        ]
        missing_ids = sorted(required_ids - covered_ids)
        eligible_evidence = [
            item
            for item in evidence
            if all(
                expression.casefold()
                in {value.casefold() for value in item.temporal_constraints_satisfied}
                for expression in required_constraint_values
            )
            and (
                not required_entities
                or any(_mentions(item, entity) for entity in required_entities)
            )
        ]
        coverage_components: list[float] = []
        if required_ids:
            coverage_components.append(len(required_ids & covered_ids) / len(required_ids))
        if required_entities:
            coverage_components.append(len(covered_entities) / len(required_entities))
        if required_constraint_values:
            coverage_components.append(len(covered_constraints) / len(required_constraint_values))
        if plan.answer_shape.value in {"table", "list", "count"}:
            coverage_components.append(
                min(1.0, len(eligible_evidence) / max(1, plan.required_evidence_count))
            )
        coverage_score = (
            sum(coverage_components) / len(coverage_components)
            if coverage_components
            else float(bool(evidence))
        )
        answerable = (
            bool(evidence)
            and len(eligible_evidence) >= plan.required_evidence_count
            and (not required_constraint_values or bool(eligible_evidence))
            and not missing_ids
            and not missing_entities
            and not missing_constraints
        )
        required_evidence = [item for item in evidence if item.evidence_id in required_ids]
        table_evidence = [
            *eligible_evidence,
            *[
                item
                for item in required_evidence
                if item not in eligible_evidence
            ],
        ] or evidence
        columns, rows = _table_rows(table_evidence)
        if evidence:
            for row in _context_table_rows(context):
                normalized = {str(key): _safe_value(value) for key, value in row.items()}
                if normalized not in rows:
                    rows.append(normalized)
        columns = _table_columns(rows)
        coverage = EvidenceCoverage(
            required_evidence_ids=sorted(required_ids),
            covered_evidence_ids=[item.evidence_id for item in evidence if item.evidence_id in required_ids],
            missing_evidence_ids=missing_ids,
            required_entities=required_entities,
            covered_entities=covered_entities,
            missing_entities=missing_entities,
            required_constraints=required_constraint_values,
            covered_constraints=covered_constraints,
            missing_constraints=missing_constraints,
            score=min(1.0, max(0.0, coverage_score)),
        )
        aggregate_temporal: dict[str, Any] = {}
        aggregate_structured: dict[str, Any] = {}
        for item in evidence:
            for key, value in item.temporal_metadata.items():
                aggregate_temporal.setdefault(key, value)
            if item.structured_data is not None:
                aggregate_structured[item.evidence_id] = item.structured_data
        confidence = (
            sum(item.confidence for item in evidence) / len(evidence)
            if evidence
            else 0.0
        )
        return ContextPackage(
            query=query_text,
            query_plan=plan,
            intent=plan.intent.value,
            answer_shape=plan.answer_shape.value,
            evidence=evidence,
            evidence_ids=[item.evidence_id for item in evidence],
            source_ids=list(dict.fromkeys(source_id for item in evidence for source_id in item.source_ids)),
            confidence=confidence,
            answerable=answerable,
            answerability=answerable,
            answerability_score=coverage.score,
            evidence_coverage=coverage,
            table=StructuredTable(columns=columns, rows=rows) if rows else None,
            table_rows=rows,
            structured_data=aggregate_structured or None,
            temporal_metadata=aggregate_temporal,
            required_evidence_ids=sorted(required_ids),
            covered_evidence_ids=coverage.covered_evidence_ids,
            missing_evidence_ids=missing_ids,
            answer_value=len(eligible_evidence) if plan.answer_shape.value == "count" else None,
            metadata={
                "retrieval_order_preserved": True,
                "required_evidence_retained": (
                    not missing_ids and len(eligible_evidence) >= plan.required_evidence_count
                ),
                "explicit_constraints": required_constraint_values,
                "eligible_evidence_ids": [item.evidence_id for item in eligible_evidence],
                "structured_table": bool(rows),
            },
        )

    def build_from_context(
        self,
        query: str | QueryPlan,
        context: Any,
        *,
        query_plan: QueryPlan | None = None,
        required_evidence_ids: Sequence[str] = (),
        token_budget: int | None = None,
    ) -> ContextPackage:
        return self.build(
            query,
            query_plan=query_plan,
            required_evidence_ids=required_evidence_ids,
            token_budget=token_budget,
            context=context,
        )


PackageBuilder = ContextPackageBuilder
ContextPackageFactory = ContextPackageBuilder


def build_context_package(
    query: str | QueryPlan,
    results: Sequence[Any] = (),
    *,
    query_plan: QueryPlan | None = None,
    required_evidence_ids: Sequence[str] = (),
    token_budget: int | None = None,
    context: Any = None,
) -> ContextPackage:
    return ContextPackageBuilder().build(
        query,
        results,
        query_plan=query_plan,
        required_evidence_ids=required_evidence_ids,
        token_budget=token_budget,
        context=context,
    )


__all__ = [
    "ContextEvidence",
    "ContextPackage",
    "ContextPackageBuilder",
    "ContextPackageFactory",
    "ContextTable",
    "Evidence",
    "EvidenceCoverage",
    "PackageBuilder",
    "StructuredTable",
    "build_context_package",
]
