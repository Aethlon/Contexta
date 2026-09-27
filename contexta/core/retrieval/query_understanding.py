from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QueryIntent(str, Enum):
    FACT = "fact"
    TEMPORAL = "temporal"
    TABLE = "table"
    LIST = "list"
    COUNT = "count"
    COMPARISON = "comparison"
    UNKNOWN = "unknown"


class AnswerShape(str, Enum):
    TEXT = "text"
    TABLE = "table"
    LIST = "list"
    COUNT = "count"


class TemporalConstraint(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    kind: str
    expression: str
    start: datetime | None = None
    end: datetime | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None
    explicit: bool = True

    @model_validator(mode="after")
    def normalize_expression(self) -> TemporalConstraint:
        self.expression = " ".join(self.expression.strip().split())
        if not self.expression:
            raise ValueError("temporal constraint expression cannot be empty")
        return self

    @property
    def label(self) -> str:
        return self.expression

    @property
    def is_range(self) -> bool:
        return self.start is not None and self.end is not None


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    query_text: str = ""
    query: str | None = None
    entities: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    temporal_constraints: list[TemporalConstraint] = Field(default_factory=list)
    temporal_constraint: TemporalConstraint | None = None
    intent: QueryIntent = QueryIntent.FACT
    answer_shape: AnswerShape = AnswerShape.TEXT
    explicit_constraints: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_evidence_count: int = Field(default=1, ge=1, le=20)
    graph_depth: int = Field(default=0, ge=0, le=5)
    include_cold: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("entity_ids", "required_evidence_ids", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, UUID, int)):
            return [str(value)]
        return [str(item) for item in value if item is not None]

    @model_validator(mode="after")
    def synchronize_contract(self) -> QueryPlan:
        if not self.query_text and self.query:
            self.query_text = self.query
        if not self.query:
            self.query = self.query_text
        if not self.query_text and isinstance(self.metadata.get("query"), str):
            self.query_text = self.metadata["query"]
            self.query = self.query_text
        if self.temporal_constraint is None and self.temporal_constraints:
            self.temporal_constraint = next(
                (item for item in self.temporal_constraints if item.explicit),
                self.temporal_constraints[0],
            )
        elif self.temporal_constraint is not None and self.temporal_constraint not in self.temporal_constraints:
            self.temporal_constraints = [*self.temporal_constraints, self.temporal_constraint]
        extra_constraints = self.__pydantic_extra__ or {}
        if not self.explicit_constraints:
            candidate = extra_constraints.get("constraints")
            if isinstance(candidate, list):
                self.explicit_constraints = [
                    str(item) for item in candidate if isinstance(item, (str, int, float))
                ]
        if not self.temporal_constraints and self.explicit_constraints:
            parsed_constraints: list[TemporalConstraint] = []
            for expression in self.explicit_constraints:
                parsed_constraints.extend(
                    item
                    for item in parse_temporal_constraints(str(expression))
                    if item.explicit
                )
            self.temporal_constraints = _deduplicate_constraints(parsed_constraints)
        if self.temporal_constraint is None and self.temporal_constraints:
            self.temporal_constraint = next(
                (item for item in self.temporal_constraints if item.explicit),
                self.temporal_constraints[0],
            )
        if not self.explicit_constraints:
            self.explicit_constraints = [
                item.expression for item in self.temporal_constraints if item.explicit
            ]
        self.explicit_constraints = list(dict.fromkeys(self.explicit_constraints))
        self.required_evidence_ids = list(dict.fromkeys(self.required_evidence_ids))
        self.entities = list(dict.fromkeys(self.entities))
        self.entity_ids = list(dict.fromkeys(self.entity_ids))
        return self

    @property
    def constraints(self) -> list[str]:
        return self.explicit_constraints

    @property
    def entity_names(self) -> list[str]:
        return self.entities

    @property
    def temporal(self) -> TemporalConstraint | None:
        return self.temporal_constraint

    @property
    def has_temporal_constraints(self) -> bool:
        return bool(self.temporal_constraints)

    @property
    def explicit_temporal_constraints(self) -> list[TemporalConstraint]:
        return [item for item in self.temporal_constraints if item.explicit]

    @property
    def requires_temporal(self) -> bool:
        return self.has_temporal_constraints or self.intent == QueryIntent.TEMPORAL

    @property
    def requires_graph(self) -> bool:
        return self.graph_depth > 0 or self.intent == QueryIntent.COMPARISON

    @property
    def requires_entity_coverage(self) -> bool:
        return bool(
            self.entities
            and (
                self.intent in {
                    QueryIntent.TABLE,
                    QueryIntent.LIST,
                    QueryIntent.COUNT,
                    QueryIntent.COMPARISON,
                }
                or len(self.entities) > 1
            )
        )

    @property
    def is_table(self) -> bool:
        return self.answer_shape == AnswerShape.TABLE

    @property
    def is_list(self) -> bool:
        return self.answer_shape == AnswerShape.LIST

    @property
    def is_count(self) -> bool:
        return self.answer_shape == AnswerShape.COUNT

    @property
    def retrieval_limit_hint(self) -> int:
        if self.answer_shape == AnswerShape.TABLE:
            hint = 8
        elif self.answer_shape == AnswerShape.LIST:
            hint = 6
        elif self.answer_shape == AnswerShape.COUNT:
            hint = 10
        else:
            hint = 3
        return max(hint, self.required_evidence_count)


MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
MONTH_INDEX = {name: index for index, name in enumerate(MONTHS, 1)}
MONTH_PATTERN = "|".join(MONTHS)

ENTITY_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "any",
    "are",
    "at",
    "be",
    "before",
    "between",
    "both",
    "by",
    "compare",
    "comparison",
    "count",
    "current",
    "did",
    "do",
    "does",
    "each",
    "event",
    "events",
    "for",
    "from",
    "give",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "list",
    "many",
    "me",
    "month",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "name",
    "number",
    "of",
    "on",
    "or",
    "project",
    "show",
    "table",
    "tell",
    "the",
    "their",
    "this",
    "to",
    "total",
    "what",
    "when",
    "where",
    "which",
    "who",
    "whose",
    "why",
    "with",
    "year",
}

COUNT_MARKERS = {
    "count",
    "number",
    "many",
    "quantity",
    "total",
}
TABLE_MARKERS = {
    "breakdown",
    "columns",
    "matrix",
    "row",
    "rows",
    "spreadsheet",
    "table",
    "tabular",
}
LIST_MARKERS = {
    "all",
    "enumerate",
    "list",
    "name",
    "show",
    "which",
}
COMPARISON_MARKERS = {
    "common",
    "compare",
    "comparison",
    "difference",
    "intersection",
    "overlap",
    "shared",
    "similar",
    "similarities",
    "versus",
    "vs",
}
TEMPORAL_MARKERS = {
    "after",
    "before",
    "current",
    "currently",
    "during",
    "earlier",
    "first",
    "history",
    "last",
    "latest",
    "next",
    "previous",
    "recent",
    "since",
    "then",
    "timeline",
    "until",
    "when",
    "while",
    "year",
    "yesterday",
    "today",
    "tomorrow",
}
RELATIONSHIP_MARKERS = {
    "between",
    "connected",
    "depends",
    "relationship",
    "related",
    "with",
}


def _as_text(value: str | Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    for name in ("query_text", "query", "text", "focus"):
        candidate = getattr(value, name, None)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if isinstance(value, Mapping):
        for name in ("query_text", "query", "text", "focus"):
            candidate = value.get(name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return str(value).strip()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _date_bound(
    year: int,
    month: int,
    day: int,
    *,
    end: bool = False,
) -> datetime:
    if end and day == calendar.monthrange(year, month)[1]:
        return datetime(year, month, day, 23, 59, 59, 999999, tzinfo=UTC)
    if end:
        return datetime(year, month, day, tzinfo=UTC) + timedelta(days=1)
    return datetime(year, month, day, tzinfo=UTC)


def _parse_date_text(
    value: str,
    now: datetime,
) -> tuple[datetime, datetime, int | None, int | None, int | None] | None:
    text = " ".join(value.strip().casefold().split())
    text = text.rstrip("?!.,;:'\"")
    text = re.sub(r"^(?:the\s+)?(?:beginning|start)\s+of\s+", "", text)
    text = re.sub(r"^(?:the\s+)?", "", text)
    if not text:
        return None

    iso_match = re.fullmatch(r"(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})", text)
    if iso_match:
        year = int(iso_match.group("year"))
        month = int(iso_match.group("month"))
        day = int(iso_match.group("day"))
        try:
            return _date_bound(year, month, day), _date_bound(year, month, day, end=True), year, month, day
        except ValueError:
            return None

    slash_match = re.fullmatch(
        r"(?P<month>\d{1,2})[-/](?P<day>\d{1,2})[-/](?P<year>\d{4})",
        text,
    )
    if slash_match:
        year = int(slash_match.group("year"))
        month = int(slash_match.group("month"))
        day = int(slash_match.group("day"))
        try:
            return _date_bound(year, month, day), _date_bound(year, month, day, end=True), year, month, day
        except ValueError:
            return None

    month_day_year = re.fullmatch(
        rf"(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?",
        text,
    )
    if month_day_year:
        month = MONTH_INDEX[month_day_year.group("month")]
        day = int(month_day_year.group("day"))
        year = int(month_day_year.group("year") or now.year)
        try:
            return _date_bound(year, month, day), _date_bound(year, month, day, end=True), year, month, day
        except ValueError:
            return None

    day_month_year = re.fullmatch(
        rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTH_PATTERN})(?:,?\s+(?P<year>\d{{4}}))?",
        text,
    )
    if day_month_year:
        month = MONTH_INDEX[day_month_year.group("month")]
        day = int(day_month_year.group("day"))
        year = int(day_month_year.group("year") or now.year)
        try:
            return _date_bound(year, month, day), _date_bound(year, month, day, end=True), year, month, day
        except ValueError:
            return None

    month_year = re.fullmatch(
        rf"(?P<month>{MONTH_PATTERN})\s+(?P<year>\d{{4}})",
        text,
    )
    if month_year:
        year = int(month_year.group("year"))
        month = MONTH_INDEX[month_year.group("month")]
        start = _date_bound(year, month, 1)
        next_month = month + 1
        end = _date_bound(year + 1, 1, 1) if next_month == 13 else _date_bound(year, next_month, 1)
        return start, end, year, month, None

    month_only = re.fullmatch(rf"(?P<month>{MONTH_PATTERN})", text)
    if month_only:
        year = now.year
        month = MONTH_INDEX[month_only.group("month")]
        start = _date_bound(year, month, 1)
        next_month = month + 1
        end = _date_bound(year + 1, 1, 1) if next_month == 13 else _date_bound(year, next_month, 1)
        return start, end, year, month, None

    year_match = re.fullmatch(r"(?P<year>(?:19|20)\d{2})", text)
    if year_match:
        year = int(year_match.group("year"))
        return _date_bound(year, 1, 1), _date_bound(year + 1, 1, 1), year, None, None

    return None


def _relative_constraint(expression: str, now: datetime) -> TemporalConstraint | None:
    text = " ".join(expression.casefold().split())
    today = _utc(now).date()
    start: datetime | None = None
    end: datetime | None = None
    if "yesterday" in text:
        start = datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    elif "today" in text or "tonight" in text:
        start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)
    elif "last week" in text or "past week" in text:
        monday = today - timedelta(days=today.weekday() + 7)
        start = datetime.combine(monday, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=7)
    elif "this week" in text:
        monday = today - timedelta(days=today.weekday())
        start = datetime.combine(monday, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=7)
    elif "last month" in text or "past month" in text:
        first = today.replace(day=1)
        previous_start = (first - timedelta(days=1)).replace(day=1)
        start = datetime.combine(previous_start, datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
    elif "this month" in text:
        first = today.replace(day=1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        start = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(next_month, datetime.min.time(), tzinfo=UTC)
    elif "last year" in text or "past year" in text:
        start = datetime(today.year - 1, 1, 1, tzinfo=UTC)
        end = datetime(today.year, 1, 1, tzinfo=UTC)
    elif "this year" in text:
        start = datetime(today.year, 1, 1, tzinfo=UTC)
        end = datetime(today.year + 1, 1, 1, tzinfo=UTC)
    else:
        relative_days = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)\b", text)
        recent = re.search(r"\b(?:recent|latest|lately)\b", text)
        if relative_days is not None:
            amount = int(relative_days.group(1))
            unit = relative_days.group(2).rstrip("s")
            if unit == "day":
                delta = timedelta(days=amount)
            elif unit == "week":
                delta = timedelta(weeks=amount)
            elif unit == "month":
                delta = timedelta(days=30 * amount)
            else:
                delta = timedelta(days=365 * amount)
            start = _utc(now) - delta
            end = _utc(now) + timedelta(days=1)
        elif recent is not None:
            start = _utc(now) - timedelta(days=30)
            end = _utc(now) + timedelta(days=1)
        else:
            return None
    return TemporalConstraint(
        kind="relative",
        expression=expression,
        start=start,
        end=end,
        explicit=True,
    )


def _deduplicate_constraints(constraints: list[TemporalConstraint]) -> list[TemporalConstraint]:
    result: list[TemporalConstraint] = []
    seen: set[tuple[str, str, str, str]] = set()
    for constraint in constraints:
        key = (
            constraint.kind,
            constraint.expression.casefold(),
            constraint.start.isoformat() if constraint.start else "",
            constraint.end.isoformat() if constraint.end else "",
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(constraint)
    return result


def parse_temporal_constraints(
    query_text: str,
    *,
    now: datetime | None = None,
) -> list[TemporalConstraint]:
    reference = _utc(now or datetime.now(UTC))
    text = " ".join(query_text.casefold().split())
    if not text:
        return []
    constraints: list[TemporalConstraint] = []
    consumed_spans: list[tuple[int, int]] = []

    range_patterns = (
        re.compile(
            r"\b(?:between|from)\s+(?P<left>.+?)\s+(?:and|to|through|until)\s+(?P<right>.+?)(?=\s+(?:and|but|with|during|for|in|on|from|between)\b|$)"
        ),
        re.compile(
            r"\b(?:after|since|before|until)\s+(?P<value>.+?)(?=\s+(?:and|but|with|during|for|in|on|from|between)\b|$)"
        ),
    )
    for pattern in range_patterns:
        for match in pattern.finditer(text):
            left_text = match.groupdict().get("left")
            right_text = match.groupdict().get("right")
            value_text = match.groupdict().get("value")
            if left_text and right_text:
                left = _parse_date_text(left_text, reference)
                right = _parse_date_text(right_text, reference)
                if left and right:
                    constraints.append(
                        TemporalConstraint(
                            kind="range",
                            expression=match.group(0).rstrip("?!.,;:'\"") ,
                            start=min(left[0], right[0]),
                            end=max(left[1], right[1]),
                            explicit=True,
                        )
                    )
                    consumed_spans.append(match.span())
                    continue
            if value_text:
                parsed = _parse_date_text(value_text, reference)
                if parsed:
                    start, end, year, month, day = parsed
                    expression = match.group(0).rstrip("?!.,;:'\"")
                    if "after" in expression or "since" in expression:
                        kind = "after" if "after" in expression else "since"
                        lower, upper = end, None
                    else:
                        kind = "before" if "before" in expression else "until"
                        lower, upper = None, start
                    constraints.append(
                        TemporalConstraint(
                            kind=kind,
                            expression=expression,
                            start=lower,
                            end=upper,
                            year=year,
                            month=month,
                            day=day,
                            explicit=True,
                        )
                    )
                    consumed_spans.append(match.span())

    date_patterns = (
        re.compile(r"\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b"),
        re.compile(r"\b\d{1,2}/\d{1,2}/(?:19|20)\d{2}\b"),
        re.compile(rf"\b(?:{MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+(?:19|20)\d{{2}})?\b"),
        re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_PATTERN})(?:,?\s+(?:19|20)\d{{2}})?\b"),
        re.compile(rf"\b(?:{MONTH_PATTERN})\s+(?:19|20)\d{{2}}\b"),
        re.compile(rf"\b(?:{MONTH_PATTERN})\b"),
        re.compile(r"\b(?:19|20)\d{2}\b"),
    )
    for pattern in date_patterns:
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in consumed_spans):
                continue
            parsed = _parse_date_text(match.group(0), reference)
            if parsed:
                start, end, year, month, day = parsed
                prefix = text[max(0, match.start() - 12):match.start()].strip()
                expression = match.group(0)
                if re.search(r"\b(?:in|during|throughout|within)\s*$", prefix):
                    expression = f"{prefix.split()[-1]} {expression}"
                constraints.append(
                    TemporalConstraint(
                        kind="date",
                        expression=expression,
                        start=start,
                        end=end,
                        year=year,
                        month=month,
                        day=day,
                        explicit=True,
                    )
                )
                consumed_spans.append(match.span())

    relative_expressions = (
        "yesterday",
        "today",
        "tonight",
        "last week",
        "past week",
        "this week",
        "last month",
        "past month",
        "this month",
        "last year",
        "past year",
        "this year",
        "recent",
        "latest",
        "lately",
    )
    for expression in relative_expressions:
        match = re.search(rf"\b{re.escape(expression)}\b", text)
        if match is None:
            continue
        constraint = _relative_constraint(expression, reference)
        if constraint is not None:
            constraints.append(constraint)
    for match in re.finditer(r"\b(?:last|past)\s+\d+\s+(?:day|days|week|weeks|month|months|year|years)\b", text):
        constraint = _relative_constraint(match.group(0), reference)
        if constraint is not None:
            constraints.append(constraint)

    if not constraints:
        marker = next((item for item in TEMPORAL_MARKERS if re.search(rf"\b{re.escape(item)}\b", text)), None)
        if marker is not None:
            constraints.append(TemporalConstraint(kind="marker", expression=marker, explicit=False))
    return _deduplicate_constraints(constraints)


def _known_entity_parts(known: Any) -> tuple[str | None, list[str], str | None]:
    if isinstance(known, Mapping):
        name = known.get("name")
        aliases = known.get("aliases", [])
        identifier = known.get("id", known.get("entity_id"))
        if name is None and len(known) == 1:
            name, identifier = next(iter(known.items()))
    else:
        name = getattr(known, "name", known if isinstance(known, str) else None)
        aliases = getattr(known, "aliases", []) or []
        identifier = getattr(known, "id", None)
    if not isinstance(name, str):
        name = None
    if isinstance(aliases, str):
        aliases = [aliases]
    if not isinstance(aliases, Sequence):
        aliases = []
    return name, [item for item in aliases if isinstance(item, str)], str(identifier) if identifier is not None else None


def extract_entities(
    query_text: str,
    *,
    known_entities: Sequence[str | Any] = (),
) -> list[str]:
    names: list[str] = []
    lowered = query_text.casefold()

    def add(value: str) -> None:
        normalized = " ".join(value.strip().split()).strip(".,;:!?()[]{}\"'")
        normalized = re.sub(r"['’]s$", "", normalized, flags=re.IGNORECASE)
        if len(normalized) < 2 or normalized.casefold() in ENTITY_STOPWORDS:
            return
        if normalized.casefold() not in {item.casefold() for item in names}:
            names.append(normalized)

    for match in re.finditer(r"[\"']([A-Za-z0-9][A-Za-z0-9 _'’\-]{1,48})[\"']", query_text):
        add(match.group(1))
    for match in re.finditer(
        r"\b[A-Z][A-Za-z0-9'’\-]{1,}(?:\s+[A-Z][A-Za-z0-9'’\-]{1,})*\b",
        query_text,
    ):
        candidate = match.group(0)
        parts = candidate.split()
        if any(part.casefold() in ENTITY_STOPWORDS for part in parts):
            for part in parts:
                add(part)
        else:
            add(candidate)
    for known in known_entities:
        name, aliases, _ = _known_entity_parts(known)
        for candidate in [name, *aliases]:
            if candidate and re.search(rf"(?<!\w){re.escape(candidate.casefold())}(?!\w)", lowered):
                add(candidate)
    return names


def _entity_ids_for_names(names: Sequence[str], known_entities: Sequence[str | Any]) -> list[str]:
    result: list[str] = []
    lowered_names = [name.casefold() for name in names]
    for known in known_entities:
        name, aliases, identifier = _known_entity_parts(known)
        if identifier is None:
            continue
        candidates = [name, *aliases]
        if any(
            candidate
            and any(
                re.search(rf"(?<!\w){re.escape(candidate.casefold())}(?!\w)", name_text)
                for name_text in lowered_names
            )
            for candidate in candidates
        ):
            result.append(identifier)
    return list(dict.fromkeys(result))


def _has_marker(text: str, markers: set[str]) -> bool:
    words = set(re.findall(r"[a-z]+", text))
    return bool(words.intersection(markers)) or any(
        re.search(rf"\b{re.escape(marker)}\b", text) for marker in markers
    )


def _looks_like_list(text: str) -> bool:
    return bool(
        re.search(r"\b(?:list|enumerate|show me|name the)\b", text)
        or re.search(r"\b(?:what|which)\s+(?:are|were)\b", text)
        or re.search(r"\b(?:what|which)\s+[a-z]+s\b", text)
    )


def _classify(
    query_text: str,
    *,
    entities: Sequence[str],
    constraints: Sequence[TemporalConstraint],
) -> tuple[QueryIntent, AnswerShape, int, int, bool]:
    text = query_text.casefold()
    has_temporal = bool(constraints) or _has_marker(text, TEMPORAL_MARKERS)
    if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b|\bquantity\b|\btotal\b", text):
        intent = QueryIntent.COUNT
        shape = AnswerShape.COUNT
        required = 5
    elif _has_marker(text, TABLE_MARKERS) or re.search(r"\bside by side\b", text):
        intent = QueryIntent.TABLE
        shape = AnswerShape.TABLE
        required = max(4, len(entities) * 2)
    elif _has_marker(text, COMPARISON_MARKERS):
        intent = QueryIntent.COMPARISON
        shape = AnswerShape.TABLE
        required = max(2, len(entities) or 2)
    elif _looks_like_list(text):
        intent = QueryIntent.LIST
        shape = AnswerShape.LIST
        required = max(3, len(entities) + 1)
    elif has_temporal:
        intent = QueryIntent.TEMPORAL
        shape = AnswerShape.TEXT
        required = 2
    elif _has_marker(text, LIST_MARKERS):
        intent = QueryIntent.LIST
        shape = AnswerShape.LIST
        required = max(3, len(entities) + 1)
    else:
        intent = QueryIntent.FACT
        shape = AnswerShape.TEXT
        required = 1
    if _has_marker(text, RELATIONSHIP_MARKERS) or len(entities) > 1 or intent == QueryIntent.COMPARISON:
        graph_depth = 2
    elif entities or has_temporal:
        graph_depth = 1
    else:
        graph_depth = 0
    return intent, shape, min(20, required), graph_depth, has_temporal


def build_query_plan(
    query: str | Any,
    *,
    known_entities: Sequence[str | Any] = (),
    entity_ids: Sequence[str | Any] = (),
    now: datetime | None = None,
) -> QueryPlan:
    text = _as_text(query)
    reference = _utc(now or datetime.now(UTC))
    entities = extract_entities(text, known_entities=known_entities)
    constraints = parse_temporal_constraints(text, now=reference)
    intent, shape, required, graph_depth, has_temporal = _classify(
        text,
        entities=entities,
        constraints=constraints,
    )
    explicit_constraints = list(
        dict.fromkeys(item.expression for item in constraints if item.explicit)
    )
    resolved_ids = _entity_ids_for_names(entities, known_entities)
    resolved_ids.extend(str(item) for item in entity_ids if item is not None)
    return QueryPlan(
        query_text=text,
        query=text,
        entities=entities,
        entity_ids=list(dict.fromkeys(resolved_ids)),
        temporal_constraints=constraints,
        temporal_constraint=next(
            (constraint for constraint in constraints if constraint.explicit),
            constraints[0] if constraints else None,
        ),
        intent=intent,
        answer_shape=shape,
        explicit_constraints=explicit_constraints,
        required_evidence_count=required,
        graph_depth=graph_depth,
        include_cold=has_temporal,
        metadata={
            "entities_detected": len(entities),
            "temporal_constraints_detected": len(constraints),
            "retrieval_mode": "query_aware",
        },
    )


def plan_query(
    query: str | Any,
    *,
    known_entities: Sequence[str | Any] = (),
    entity_ids: Sequence[str | Any] = (),
    now: datetime | None = None,
) -> QueryPlan:
    return build_query_plan(
        query,
        known_entities=known_entities,
        entity_ids=entity_ids,
        now=now,
    )


class QueryUnderstanding:
    def __init__(
        self,
        *,
        now: datetime | None = None,
        known_entities: Sequence[str | Any] = (),
    ) -> None:
        self.now = _utc(now or datetime.now(UTC))
        self.known_entities = known_entities

    def plan(
        self,
        query: str | Any,
        *,
        known_entities: Sequence[str | Any] | None = None,
        entity_ids: Sequence[str | Any] = (),
        now: datetime | None = None,
    ) -> QueryPlan:
        return build_query_plan(
            query,
            known_entities=known_entities if known_entities is not None else self.known_entities,
            entity_ids=entity_ids,
            now=now or self.now,
        )

    def understand(
        self,
        query: str | Any,
        *,
        known_entities: Sequence[str | Any] | None = None,
        entity_ids: Sequence[str | Any] = (),
        now: datetime | None = None,
    ) -> QueryPlan:
        return self.plan(
            query,
            known_entities=known_entities,
            entity_ids=entity_ids,
            now=now,
        )

    def __call__(
        self,
        query: str | Any,
        *,
        known_entities: Sequence[str | Any] | None = None,
        entity_ids: Sequence[str | Any] = (),
        now: datetime | None = None,
    ) -> QueryPlan:
        return self.plan(
            query,
            known_entities=known_entities,
            entity_ids=entity_ids,
            now=now,
        )


QueryPlanner = QueryUnderstanding
QueryUnderstandingEngine = QueryUnderstanding
understand_query = build_query_plan


__all__ = [
    "AnswerShape",
    "QueryIntent",
    "QueryPlan",
    "QueryPlanner",
    "QueryUnderstanding",
    "QueryUnderstandingEngine",
    "TemporalConstraint",
    "build_query_plan",
    "extract_entities",
    "parse_temporal_constraints",
    "plan_query",
    "understand_query",
]
