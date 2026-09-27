from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

DateInput = datetime | date | str | None
TimezoneInput = str | tzinfo | None

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "a couple": 2,
    "a couple of": 2,
    "couple": 2,
    "couple of": 2,
    "a few": 3,
    "few": 3,
    "several": 3,
}

_MONTH_NAME_PATTERN = (
    r"(?:january|jan|february|feb|march|mar|april|apr|may|"
    r"june|jun|july|jul|august|aug|september|sept|sep|"
    r"october|oct|november|nov|december|dec)"
)
_DAY_PATTERN = r"\d{1,2}(?:st|nd|rd|th)?"
_YEAR_PATTERN = r"\d{4}"
_ISO_DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"
_YEAR_FIRST_SLASH_DATE_PATTERN = r"\d{4}/\d{1,2}/\d{1,2}"
_DAY_FIRST_DATE_PATTERN = rf"{_DAY_PATTERN}\s+{_MONTH_NAME_PATTERN},?\s+{_YEAR_PATTERN}"
_MONTH_FIRST_DATE_PATTERN = rf"{_MONTH_NAME_PATTERN}\s+{_DAY_PATTERN},?\s+{_YEAR_PATTERN}"
_MONTH_YEAR_PATTERN = rf"{_MONTH_NAME_PATTERN}\s*,?\s*{_YEAR_PATTERN}"
_NATURAL_DATE_PATTERN = rf"(?:{_DAY_FIRST_DATE_PATTERN}|{_MONTH_FIRST_DATE_PATTERN}|{_MONTH_YEAR_PATTERN})"
_WEEKDAY_PATTERN = "|".join(_WEEKDAYS)
_NUMBER_PATTERN = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_WEEK_BEFORE_TARGET_PATTERN = (
    rf"(?:{_DAY_FIRST_DATE_PATTERN}|{_MONTH_FIRST_DATE_PATTERN}|{_ISO_DATE_PATTERN}|{_YEAR_FIRST_SLASH_DATE_PATTERN}|"
    rf"{_MONTH_YEAR_PATTERN}|in\s+{_YEAR_PATTERN}|{_YEAR_PATTERN}|"
    r"yesterday|today|tomorrow|"
    rf"(?:last|this|next)\s+(?:week|month|year|{_WEEKDAY_PATTERN})|"
    rf"(?:{_NUMBER_PATTERN})\s+(?:day|week|month|year)s?\s+ago|"
    rf"{_WEEKDAY_PATTERN})"
)

_EXPRESSION_RE = re.compile(
    rf"\b(?P<week_before>week\s+before\s+{_WEEK_BEFORE_TARGET_PATTERN})\b"
    r"|\b(?P<day_word>yesterday|today|tomorrow)\b"
    r"|\b(?P<period_direction>last|this|next)\s+(?P<period_unit>week|month|year)\b"
    r"|\b(?P<weekday_direction>last|this|next)\s+"
    rf"(?P<weekday_name>{_WEEKDAY_PATTERN})\b"
    rf"|\b(?P<ago_count>{_NUMBER_PATTERN})\s+"
    r"(?P<ago_unit>day|week|month|year)s?\s+ago\b"
    rf"|\b(?P<weekday_only>{_WEEKDAY_PATTERN})\b"
    rf"|\b(?P<explicit_date>{_ISO_DATE_PATTERN})\b"
    rf"|\b(?P<explicit_slash_date>{_YEAR_FIRST_SLASH_DATE_PATTERN})\b"
    rf"|\b(?P<natural_date>{_NATURAL_DATE_PATTERN})\b"
    rf"|\b(?P<year_only>in\s+{_YEAR_PATTERN})\b",
    re.IGNORECASE,
)

_NATURAL_DATE_PARTS_RE = re.compile(
    rf"^(?:"
    rf"(?P<day_first_day>{_DAY_PATTERN})\s+(?P<day_first_month>{_MONTH_NAME_PATTERN})"
    rf"|(?P<month_first_month>{_MONTH_NAME_PATTERN})\s+(?P<month_first_day>{_DAY_PATTERN})"
    rf"|(?P<month_only>{_MONTH_NAME_PATTERN})"
    rf")\s*,?\s*(?P<year>{_YEAR_PATTERN})$",
    re.IGNORECASE,
)
_YEAR_ONLY_RE = re.compile(r"^in\s+(?P<year>\d{4})$", re.IGNORECASE)
_ISO_DATETIME_PATTERN = (
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
    r"(?:\s?(?:[AP]M|UTC|GMT|Z|[+-]\d{2}:?\d{2}))?)?"
)
_TIME_PATTERN = (
    r"(?:\d{1,2}(?::\d{2})(?::\d{2}(?:\.\d+)?)?\s*(?:a\.?m\.?|p\.?m\.?)?"
    r"|\d{1,2}\s*(?:a\.?m\.?|p\.?m\.?))"
)
_ABSOLUTE_ENDPOINT_PATTERN = (
    rf"(?:{_ISO_DATETIME_PATTERN}|{_DAY_FIRST_DATE_PATTERN}|{_MONTH_FIRST_DATE_PATTERN}"
    rf"|{_MONTH_YEAR_PATTERN}|{_YEAR_FIRST_SLASH_DATE_PATTERN}|\bin\s+{_YEAR_PATTERN})"
)
_INTERVAL_SEPARATOR_PATTERN = r"(?:\bto\b|\bthrough\b|\buntil\b|\band\b|[–—])"
_INTERVAL_RE = re.compile(
    rf"(?P<interval>(?:"
    rf"(?:from|between)\s+(?P<start>{_ABSOLUTE_ENDPOINT_PATTERN})\s*"
    rf"(?:{_INTERVAL_SEPARATOR_PATTERN})\s*(?P<end>{_ABSOLUTE_ENDPOINT_PATTERN})"
    rf"|(?P<start2>{_ABSOLUTE_ENDPOINT_PATTERN})\s*"
    rf"(?:\bto\b|\bthrough\b|\buntil\b|[–—])\s*(?P<end2>{_ABSOLUTE_ENDPOINT_PATTERN})"
    rf"))"
    r"(?=\s|[.,!?;)\]]|$)",
    re.IGNORECASE,
)
_SHORT_DAY_RANGE_RE = re.compile(
    rf"(?P<short_range>(?:{_MONTH_NAME_PATTERN})\s+(?P<start>{_DAY_PATTERN})\s*"
    rf"(?:-|–|—|\bto\b|\bthrough\b)\s*(?P<end>{_DAY_PATTERN}),?\s+{_YEAR_PATTERN})"
    r"(?=\s|[.,!?;)\]]|$)",
    re.IGNORECASE,
)
_ISO_DATETIME_RE = re.compile(
    rf"(?P<iso_datetime>{_ISO_DATETIME_PATTERN})(?=\s|[.,!?;)\]]|$)",
    re.IGNORECASE,
)
_NATURAL_DATETIME_RE = re.compile(
    rf"(?P<natural_datetime>(?:{_DAY_FIRST_DATE_PATTERN}|{_MONTH_FIRST_DATE_PATTERN})"
    rf"\s+(?:at\s+)?{_TIME_PATTERN})(?=\s|[.,!?;)\]]|$)",
    re.IGNORECASE,
)
_EXTRA_RELATIVE_RE = re.compile(
    rf"(?P<extra_expression>(?:"
    rf"in\s+(?:the\s+)?(?:next\s+)?{_NUMBER_PATTERN}\s+(?:day|week|month|year)s?"
    rf"|{_NUMBER_PATTERN}\s+(?:day|week|month|year)s?\s+(?:from\s+now|later)"
    rf"|(?:over\s+)?(?:the\s+)?(?:past|last|previous)\s+{_NUMBER_PATTERN}\s+"
    rf"(?:day|week|month|year)s?"
    rf"|over\s+the\s+next\s+{_NUMBER_PATTERN}\s+(?:day|week|month|year)s?"
    rf"|(?:the\s+)?(?:next|coming)\s+{_NUMBER_PATTERN}\s+(?:day|week|month|year)s?"
    rf"|(?:the\s+)?day\s+before\s+yesterday"
    rf"|(?:the\s+)?day\s+after\s+tomorrow"
    rf"|(?:the\s+)?week\s+(?:before|after)\s+(?:last|this|next)\s+"
    rf"(?:week|month|year)"
    rf"|(?:the\s+)?week\s+of\s+{_ABSOLUTE_ENDPOINT_PATTERN}"
    rf"|(?:the\s+)?month\s+of\s+{_ABSOLUTE_ENDPOINT_PATTERN}"
    rf"|(?:today|tomorrow|yesterday)\s+at\s+{_TIME_PATTERN}"
    rf"|now"
    rf"))(?=\s|[.,!?;)\]]|$)",
    re.IGNORECASE,
)
_RELATIVE_INTERVAL_RE = re.compile(
    r"(?P<interval>(?:(?:from|between)\s+)?(?P<start>[A-Za-z0-9][A-Za-z0-9 ,'\-]*?)"
    r"\s+(?:to|through|until|and)\s+(?P<end>[A-Za-z0-9][A-Za-z0-9 ,'\-]*))"
    r"(?=\s|[.,!?;)\]]|$)",
    re.IGNORECASE,
)

_EXTENDED_COUNT_PATTERN = (
    r"(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"a\s+couple(?:\s+of)?|a\s+few|several|couple(?:\s+of)?|few)"
)
_EXTENDED_UNIT_PATTERN = r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|quarters?|years?)"
_EXTENDED_BARE_START_PATTERN = (
    r"(?:today|tonight|tomorrow|yesterday|"
    r"(?:last|this|next|previous|following|upcoming)\s+(?:week|month|quarter|year|weekend)|"
    r"(?:last|this|next|previous|following|upcoming)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"\d{4}-\d{2}-\d{2}|\d{4}/\d{1,2}/\d{1,2}|"
    r"\d{1,2}(?::\d{2})?(?:a\.?m\.?|p\.?m\.?)?)"
)
_EXTENDED_SPAN_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<extended_expression>"
    rf"(?:right\s+now|just\s+now|at\s+this\s+time|right\s+then|at\s+the\s+moment)"
    rf"|(?:the\s+)?day\s+(?:before\s+yesterday|after\s+tomorrow)"
    rf"|tonight|noon|midnight"
    rf"|(?:this|last|next|previous|following|upcoming)\s+(?:morning|afternoon|evening|night|weekend)"
    rf"|(?:last|next|previous|following|upcoming)\s+weekend"
    rf"|(?:the\s+)?(?:previous|following)\s+week"
    rf"|(?:the\s+)?week\s+(?:before|after)\s+(?:next|last|this|previous|following|upcoming)(?:\s+(?:week|month|quarter|year))?"
    rf"|(?:until|by)\s+[A-Za-z0-9][^.;!?]*"
    rf"|(?:the\s+)?(?:first|second|third|fourth)\s+quarter\s+of\s+\d{{4}}"
    rf"|(?:q[1-4]\s+\d{{4}}|\d{{4}}\s+q[1-4])"
    rf"|(?:the\s+)?(?:week|month|quarter|year)\s+(?:before|after)\s+"
    rf"(?:last|this|next|previous|following|upcoming)\s+(?:week|month|quarter|year)"
    rf"|(?:the\s+)?(?:past|last|previous|next|following|upcoming|coming)\s+"
    rf"(?:{_EXTENDED_COUNT_PATTERN}\s+)?{_EXTENDED_UNIT_PATTERN}"
    rf"|(?:over|throughout|during|for|within|in)\s+(?:the\s+)?"
    rf"(?:past|last|previous|next|following|upcoming|coming)\s+"
    rf"(?:{_EXTENDED_COUNT_PATTERN}\s+)?{_EXTENDED_UNIT_PATTERN}"
    rf"|(?:in|by)\s+(?:the\s+)?next\s+{_EXTENDED_COUNT_PATTERN}\s+{_EXTENDED_UNIT_PATTERN}"
    rf"|(?:for|over|throughout|during|within)\s+(?:the\s+)?"
    rf"{_EXTENDED_COUNT_PATTERN}\s+{_EXTENDED_UNIT_PATTERN}"
    rf"|(?:in|after|before)\s+(?:the\s+)?{_EXTENDED_COUNT_PATTERN}\s+{_EXTENDED_UNIT_PATTERN}"
    rf"|(?:in|from|after|before)\s+(?:the\s+)?{_EXTENDED_COUNT_PATTERN}\s+"
    rf"{_EXTENDED_UNIT_PATTERN}\s+(?:from\s+now|from\s+today|later|hence|ago|before\s+now|after\s+now)"
    rf"|{_EXTENDED_COUNT_PATTERN}\s+{_EXTENDED_UNIT_PATTERN}\s+(?:from\s+now|from\s+today|later|hence|ago|before\s+now|after\s+now)"
    rf"|(?:now|right\s+now|just\s+now)"
    rf")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_EXTENDED_INTERVAL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<interval>"
    r"(?:from|between)\s+[A-Za-z0-9][^.;!?]*?\s+"
    r"(?:to|through|until|and)\s+[A-Za-z0-9][^.;!?]*"
    rf"|(?:{_EXTENDED_BARE_START_PATTERN})\s+(?:to|through|until)\s+[A-Za-z0-9][^.;!?]*"
    r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_EXTENDED_DASH_INTERVAL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<interval>"
    rf"(?:{_EXTENDED_BARE_START_PATTERN})\s*-\s*(?:{_EXTENDED_BARE_START_PATTERN})"
    r"|[A-Za-z0-9][^.;!?]*?\s*(?:--|–|—|\s-\s)\s*[A-Za-z0-9][^.;!?]*"
    r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


class TemporalMatch(BaseModel):
    original_expression: str
    normalized_expression: str
    resolved_at: datetime | None = None
    end_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    temporal_precision: str = "unknown"
    temporal_basis: str = "unresolved_no_reference"
    timezone: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_field_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        result = dict(value)
        if "temporal_precision" not in result and "precision" in result:
            result["temporal_precision"] = result["precision"]
        if "temporal_basis" not in result and "basis" in result:
            result["temporal_basis"] = result["basis"]
        if "source_span" not in result and isinstance(result.get("span"), Mapping):
            result["source_span"] = dict(result["span"])
        return result

    @model_validator(mode="after")
    def _synchronize_interval_fields(self) -> TemporalMatch:
        if self.event_start is None and self.resolved_at is not None:
            self.event_start = self.resolved_at
        if self.resolved_at is None and self.event_start is not None:
            self.resolved_at = self.event_start
        if self.event_end is None and self.end_at is not None:
            self.event_end = self.end_at
        if self.end_at is None and self.event_end is not None:
            self.end_at = self.event_end
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @property
    def precision(self) -> str:
        return self.temporal_precision

    @property
    def basis(self) -> str:
        return self.temporal_basis

    @property
    def event_timezone(self) -> str | None:
        return self.timezone

    @property
    def resolved_expression(self) -> str:
        return self.normalized_expression

    @property
    def start(self) -> datetime | None:
        return self.event_start or self.resolved_at

    @property
    def end(self) -> datetime | None:
        return self.event_end or self.end_at

    @property
    def span(self) -> dict[str, int] | None:
        return self.source_span


class TemporalText(BaseModel):
    original_text: str
    normalized_text: str
    reference_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    temporal_precision: str = "unknown"
    temporal_basis: str = "unavailable"
    timezone: str
    source_start: int | None = None
    source_end: int | None = None
    source_spans: list[dict[str, int]] = Field(default_factory=list)
    matches: list[TemporalMatch] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_field_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        result = dict(value)
        if "temporal_precision" not in result and "precision" in result:
            result["temporal_precision"] = result["precision"]
        if "temporal_basis" not in result and "basis" in result:
            result["temporal_basis"] = result["basis"]
        if "source_spans" not in result and isinstance(result.get("source_span"), Mapping):
            result["source_spans"] = [dict(result["source_span"])]
        return result

    @model_validator(mode="after")
    def _synchronize_source_fields(self) -> TemporalText:
        if self.source_span is None and self.source_spans:
            self.source_start = self.source_spans[0].get("start")
            self.source_end = self.source_spans[0].get("end")
        if self.source_start is None and self.source_spans:
            self.source_start = self.source_spans[0].get("start")
        if self.source_end is None and self.source_spans:
            self.source_end = self.source_spans[0].get("end")
        return self

    @property
    def resolved(self) -> bool:
        return any(match.resolved_at is not None for match in self.matches)

    @property
    def precision(self) -> str:
        return self.temporal_precision

    @property
    def basis(self) -> str:
        return self.temporal_basis

    @property
    def event_timezone(self) -> str:
        return self.timezone

    @property
    def event_at(self) -> datetime | None:
        return self.event_start

    @property
    def source_span(self) -> dict[str, int] | None:
        return self.source_spans[0] if self.source_spans else None


class TemporalMessageContext(BaseModel):
    reference_at: datetime | None = None
    occurred_at: datetime | None = None
    observed_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    source_id: str | None = None
    message_id: str | None = None
    source_message_id: str | None = None
    timezone: str = "UTC"
    temporal_precision: str = "unknown"
    temporal_basis: str = "unavailable"
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None
    matches: list[TemporalMatch] = Field(default_factory=list)
    original_text: str | None = None
    normalized_text: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_field_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        result = dict(value)
        if "temporal_precision" not in result and "precision" in result:
            result["temporal_precision"] = result["precision"]
        if "temporal_basis" not in result and "basis" in result:
            result["temporal_basis"] = result["basis"]
        if "source_span" not in result and isinstance(result.get("span"), Mapping):
            result["source_span"] = dict(result["span"])
        if "message_id" not in result and "source_message_id" in result:
            result["message_id"] = result["source_message_id"]
        return result

    @model_validator(mode="after")
    def _synchronize_interval_fields(self) -> TemporalMessageContext:
        if self.event_start is None and self.reference_at is not None:
            self.event_start = self.reference_at
        if self.source_message_id is None and self.message_id is not None:
            self.source_message_id = self.message_id
        if self.message_id is None and self.source_message_id is not None:
            self.message_id = self.source_message_id
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @property
    def precision(self) -> str:
        return self.temporal_precision

    @property
    def basis(self) -> str:
        return self.temporal_basis

    @property
    def event_timezone(self) -> str:
        return self.timezone

    @property
    def event_at(self) -> datetime | None:
        return self.event_start or self.reference_at

    @property
    def span(self) -> dict[str, int] | None:
        return self.source_span


def _coerce_timezone(value: TimezoneInput, reference: DateInput = None) -> tzinfo:
    if value is not None:
        if isinstance(value, tzinfo):
            return value
        try:
            return ZoneInfo(str(value))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
    if isinstance(reference, datetime) and reference.tzinfo is not None:
        return reference.tzinfo
    if isinstance(reference, str):
        candidate = reference.strip()
        if candidate.endswith(("Z", "z")):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            return parsed.tzinfo
    return UTC


def _coerce_datetime(value: DateInput, timezone: tzinfo) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone)
        return value.astimezone(timezone)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone)
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
    if parsed is None:
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%m/%d/%Y",
        ):
            try:
                parsed = datetime.strptime(candidate, pattern).replace(tzinfo=timezone)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _date_at(target: date, timezone: tzinfo) -> datetime:
    return datetime.combine(target, time.min, tzinfo=timezone)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _parse_absolute_expression(expression: str) -> tuple[date, date | None, str] | None:
    candidate = re.sub(r"\s+", " ", expression.strip())
    if re.fullmatch(_ISO_DATE_PATTERN, candidate, re.IGNORECASE):
        try:
            target = date.fromisoformat(candidate)
        except ValueError:
            return None
        return target, None, "day"
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", candidate):
        try:
            year, month, day = (int(part) for part in candidate.split("/"))
            return date(year, month, day), None, "day"
        except ValueError:
            return None

    year_only = _YEAR_ONLY_RE.fullmatch(candidate)
    if year_only is not None:
        try:
            year = int(year_only.group("year"))
            return date(year, 1, 1), date(year, 12, 31), "year"
        except ValueError:
            return None

    match = _NATURAL_DATE_PARTS_RE.fullmatch(candidate)
    if match is None:
        return None

    month_value = (
        match.group("day_first_month")
        or match.group("month_first_month")
        or match.group("month_only")
    )
    if month_value is None:
        return None
    month = _MONTHS.get(month_value.lower())
    if month is None:
        return None

    year = int(match.group("year"))
    day_value = match.group("day_first_day") or match.group("month_first_day")
    if day_value is None:
        try:
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), "month"
        except ValueError:
            return None

    day = int(re.sub(r"(?:st|nd|rd|th)$", "", day_value, flags=re.IGNORECASE))
    try:
        return date(year, month, day), None, "day"
    except ValueError:
        return None


def _resolved_match(
    expression: str,
    start: datetime,
    end: datetime | None,
    precision: str,
    timezone: tzinfo,
    basis: str,
    source_start: int | None = None,
    source_end: int | None = None,
) -> TemporalMatch:
    date_granularities = {"day", "week", "month", "quarter", "year"}
    start_text = start.date().isoformat() if precision in date_granularities and start.time() == time.min else start.isoformat()
    normalized_expression = start_text
    if end is not None:
        end_text = end.date().isoformat() if precision in date_granularities and end.time() == time.min else end.isoformat()
        normalized_expression = f"{start_text} through {end_text}"
    return TemporalMatch(
        original_expression=expression,
        normalized_expression=normalized_expression,
        resolved_at=start,
        end_at=end,
        event_start=start,
        event_end=end,
        temporal_precision=precision,
        temporal_basis=basis,
        timezone=str(timezone),
        source_start=source_start,
        source_end=source_end,
    )


def _resolved_date_match(
    expression: str,
    start: date,
    end: date | None,
    precision: str,
    timezone: tzinfo,
    basis: str,
) -> TemporalMatch:
    return _resolved_match(
        expression,
        _date_at(start, timezone),
        _date_at(end, timezone) if end is not None else None,
        precision,
        timezone,
        basis,
    )


def _resolve_explicit_match(expression: str, timezone: tzinfo) -> TemporalMatch | None:
    parsed = _parse_absolute_expression(expression)
    if parsed is None:
        return None
    start, end, precision = parsed
    return _resolved_date_match(expression, start, end, precision, timezone, "explicit_date")


def _number_value(value: str) -> int:
    candidate = value.casefold()
    if candidate.isdigit():
        return int(candidate)
    return _NUMBER_WORDS.get(candidate, 1)


def _shift_date(value: date, amount: int, unit: str) -> date:
    if unit == "day":
        return value + timedelta(days=amount)
    if unit == "week":
        return value + timedelta(weeks=amount)
    if unit == "month":
        return _add_months(value, amount)
    if unit == "year":
        return _add_months(value, amount * 12)
    raise ValueError(f"Unsupported temporal unit: {unit}")


def _parse_time_expression(value: str, target: date, timezone: tzinfo) -> datetime | None:
    candidate = re.sub(r"\s+", "", value.casefold()).replace(".", "")
    match = re.fullmatch(
        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?(?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?"
        r"(?P<meridiem>am|pm)?",
        candidate,
    )
    if match is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    second = int(match.group("second") or 0)
    meridiem = match.group("meridiem")
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59 or second > 59:
        return None
    microsecond = int((match.group("fraction") or "0").ljust(6, "0")[:6])
    return datetime.combine(target, time(hour, minute, second, microsecond), tzinfo=timezone)


def _parse_exact_value(expression: str, timezone: tzinfo) -> TemporalMatch | None:
    candidate = re.sub(r"\s+", " ", expression.strip())
    candidate = re.sub(r"^(?:on|at)\s+", "", candidate, flags=re.IGNORECASE)
    iso_match = _ISO_DATETIME_RE.fullmatch(candidate)
    if iso_match is not None:
        parsed = _coerce_datetime(iso_match.group("iso_datetime"), timezone)
        if parsed is not None:
            has_time = bool(re.search(r"[T ]\d{1,2}:", iso_match.group("iso_datetime")))
            return _resolved_match(
                candidate,
                parsed,
                None,
                "exact" if has_time else "day",
                timezone,
                "explicit_date",
            )
    natural_match = re.fullmatch(
        rf"(?P<date>{_DAY_FIRST_DATE_PATTERN}|{_MONTH_FIRST_DATE_PATTERN})\s+"
        rf"(?:at\s+)?(?P<time>{_TIME_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if natural_match is not None:
        parsed_date = _parse_absolute_expression(natural_match.group("date"))
        if parsed_date is not None:
            parsed_time = _parse_time_expression(natural_match.group("time"), parsed_date[0], timezone)
            if parsed_time is not None:
                return _resolved_match(candidate, parsed_time, None, "exact", timezone, "explicit_date")
    return None


def _parse_endpoint(
    expression: str,
    reference: datetime | None,
    timezone: tzinfo,
) -> TemporalMatch | None:
    candidate = re.sub(r"\s+", " ", expression.strip())
    candidate = re.sub(r"^(?:on|the)\s+", "", candidate, flags=re.IGNORECASE)
    exact = _parse_exact_value(candidate, timezone)
    if exact is not None:
        return exact
    if reference is None:
        return None
    base = _resolve_match(candidate, reference, timezone)
    if base is not None:
        return base
    if _INTERVAL_RE.fullmatch(candidate) or _RELATIVE_INTERVAL_RE.fullmatch(candidate):
        return None
    extended = _resolve_additional_expression(candidate, reference, timezone, allow_interval=False)
    if extended is not None:
        return extended
    return _resolve_extra_expression(candidate, reference, timezone)


def _interval_precision(left: TemporalMatch, right: TemporalMatch) -> str:
    rank = {
        "unknown": 0,
        "second": 1,
        "minute": 1,
        "hour": 1,
        "exact": 2,
        "day": 3,
        "week": 4,
        "month": 5,
        "quarter": 6,
        "year": 7,
    }
    return max(
        (left.temporal_precision, right.temporal_precision),
        key=lambda value: rank.get(value, 0),
    )


def _resolve_interval(
    expression: str,
    reference: datetime | None,
    timezone: tzinfo,
) -> TemporalMatch | None:
    candidate = re.sub(r"\s+", " ", expression.strip())
    short_range = _SHORT_DAY_RANGE_RE.fullmatch(candidate)
    if short_range is not None:
        month = _MONTHS.get(short_range.group(0).split()[0].casefold())
        if month is None:
            return None
        year_text = short_range.group(0).rsplit(",", 1)[-1].strip()
        year_match = re.search(rf"({_YEAR_PATTERN})$", year_text)
        if year_match is None:
            return None
        start_day = int(re.sub(r"(?:st|nd|rd|th)$", "", short_range.group("start"), flags=re.IGNORECASE))
        end_day = int(re.sub(r"(?:st|nd|rd|th)$", "", short_range.group("end"), flags=re.IGNORECASE))
        try:
            start = date(int(year_match.group(1)), month, start_day)
            end = date(int(year_match.group(1)), month, end_day)
        except ValueError:
            return None
        if end < start:
            return None
        return _resolved_match(candidate, _date_at(start, timezone), _date_at(end, timezone), "day", timezone, "explicit_date")

    week_of = re.fullmatch(
        rf"(?:the\s+)?week\s+of\s+(?P<target>{_ABSOLUTE_ENDPOINT_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if week_of is not None:
        target = _parse_endpoint(week_of.group("target"), reference, timezone)
        if target is None or target.event_start is None:
            return None
        start = target.event_start.date() - timedelta(days=target.event_start.weekday())
        end = start + timedelta(days=6)
        return _resolved_match(
            candidate,
            _date_at(start, timezone),
            _date_at(end, timezone),
            "week",
            timezone,
            target.temporal_basis,
        )

    month_of = re.fullmatch(
        rf"(?:the\s+)?month\s+of\s+(?P<target>{_ABSOLUTE_ENDPOINT_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if month_of is not None:
        target = _parse_endpoint(month_of.group("target"), reference, timezone)
        if target is None or target.event_start is None:
            return None
        start = target.event_start.date().replace(day=1)
        end = _add_months(start, 1) - timedelta(days=1)
        return _resolved_match(
            candidate,
            _date_at(start, timezone),
            _date_at(end, timezone),
            "month",
            timezone,
            target.temporal_basis,
        )

    interval_match = _INTERVAL_RE.fullmatch(candidate)
    if interval_match is not None:
        start_expression = interval_match.group("start") or interval_match.group("start2")
        end_expression = interval_match.group("end") or interval_match.group("end2")
        left = _parse_endpoint(start_expression, reference, timezone)
        right = _parse_endpoint(end_expression, reference, timezone)
    else:
        interval_match = _RELATIVE_INTERVAL_RE.fullmatch(candidate)
        if interval_match is None:
            return None
        left = _parse_endpoint(interval_match.group("start"), reference, timezone)
        right = _parse_endpoint(interval_match.group("end"), reference, timezone)
    if left is None or right is None or left.event_start is None or right.event_start is None:
        return None
    start = left.event_start
    end = right.event_end or right.event_start
    if end < start:
        return None
    basis = (
        "relative_expression"
        if left.temporal_basis == "relative_expression" or right.temporal_basis == "relative_expression"
        else "explicit_date"
    )
    return _resolved_match(candidate, start, end, _interval_precision(left, right), timezone, basis)


def _resolve_extra_expression(
    expression: str,
    reference: datetime | None,
    timezone: tzinfo,
) -> TemporalMatch | None:
    candidate = re.sub(r"\s+", " ", expression.strip())
    if re.fullmatch(r"(?:the\s+)?week\s+before\s+next\s+month", candidate, re.IGNORECASE):
        return _unresolved(candidate, "unresolved_unknown_expression", timezone)
    if reference is None:
        interval = _resolve_interval(candidate, None, timezone)
        if interval is not None:
            return interval
        exact = _parse_exact_value(candidate, timezone)
        if exact is not None:
            return exact
        return _unresolved(candidate, "unresolved_no_reference")

    local_reference = reference.astimezone(timezone)
    reference_date = local_reference.date()
    exact = _parse_exact_value(candidate, timezone)
    if exact is not None:
        return exact
    extended = _resolve_additional_expression(candidate, reference, timezone)
    if extended is not None:
        return extended
    interval = _resolve_interval(candidate, reference, timezone)
    if interval is not None:
        return interval

    now_match = re.fullmatch(r"now", candidate, re.IGNORECASE)
    if now_match is not None:
        return _resolved_match(candidate, local_reference, None, "exact", timezone, "relative_expression")

    point_match = re.fullmatch(
        rf"in\s+(?:the\s+)?(?P<count>{_NUMBER_PATTERN})\s+(?P<unit>day|week|month|year)s?"
        rf"|(?P<count2>{_NUMBER_PATTERN})\s+(?P<unit2>day|week|month|year)s?\s+(?:from\s+now|later)",
        candidate,
        re.IGNORECASE,
    )
    if point_match is not None:
        count = _number_value(point_match.group("count") or point_match.group("count2"))
        unit = (point_match.group("unit") or point_match.group("unit2")).casefold()
        target_date = _shift_date(reference_date, count, unit)
        return _resolved_date_match(candidate, target_date, None, unit, timezone, "relative_expression")

    interval_match = re.fullmatch(
        rf"(?:over\s+)?(?:the\s+)?(?P<direction>past|last|previous|next|coming)\s+"
        rf"(?P<count>{_NUMBER_PATTERN})\s+(?P<unit>day|week|month|year)s?",
        candidate,
        re.IGNORECASE,
    )
    if interval_match is not None:
        count = _number_value(interval_match.group("count"))
        unit = interval_match.group("unit").casefold()
        direction = interval_match.group("direction").casefold()
        if direction in {"past", "last", "previous"}:
            if direction == "past":
                start = _shift_date(reference_date, -(count - 1), unit)
                end = reference_date
            else:
                start = _shift_date(reference_date, -count, unit)
                end = reference_date - timedelta(days=1)
        else:
            start = _shift_date(reference_date, 0 if candidate.casefold().startswith("over") else 1, unit)
            end = _shift_date(reference_date, count, unit)
        return _resolved_match(
            candidate,
            _date_at(start, timezone),
            _date_at(end, timezone),
            unit,
            timezone,
            "relative_expression",
        )

    day_phrase = re.fullmatch(
        r"(?:the\s+)?day\s+(?P<direction>before\s+yesterday|after\s+tomorrow)",
        candidate,
        re.IGNORECASE,
    )
    if day_phrase is not None:
        amount = -2 if day_phrase.group("direction").casefold().startswith("before") else 2
        target = reference_date + timedelta(days=amount)
        return _resolved_date_match(candidate, target, None, "day", timezone, "relative_expression")

    relative_week = re.fullmatch(
        r"(?:the\s+)?week\s+(?P<direction>before|after)\s+"
        r"(?P<target>last|this|next)\s+(?P<unit>week|month|year)",
        candidate,
        re.IGNORECASE,
    )
    if relative_week is not None:
        target = _resolve_match(
            f"{relative_week.group('target')} {relative_week.group('unit')}",
            reference,
            timezone,
        )
        if target is None or target.event_start is None:
            return None
        if relative_week.group("direction").casefold() == "before":
            start_date = target.event_start.date() - timedelta(days=7)
        else:
            start_date = (target.event_end or target.event_start).date() + timedelta(days=1)
        end_date = start_date + timedelta(days=6)
        return _resolved_match(
            candidate,
            _date_at(start_date, timezone),
            _date_at(end_date, timezone),
            "week",
            timezone,
            "relative_expression",
        )

    timed_day = re.fullmatch(
        rf"(?P<day>today|tomorrow|yesterday)\s+at\s+(?P<time>{_TIME_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if timed_day is not None:
        day_match = _resolve_match(timed_day.group("day"), reference, timezone)
        if day_match is None or day_match.event_start is None:
            return None
        target = _parse_time_expression(
            timed_day.group("time"),
            day_match.event_start.date(),
            timezone,
        )
        if target is not None:
            return _resolved_match(candidate, target, None, "exact", timezone, "relative_expression")
    return None


def _extended_number(value: str) -> float | None:
    candidate = re.sub(r"\s+", " ", value.strip().casefold())
    if re.fullmatch(r"\d+(?:\.\d+)?", candidate):
        return float(candidate)
    return float(_NUMBER_WORDS.get(candidate, 0)) if candidate in _NUMBER_WORDS else None


def _extended_unit(value: str) -> str:
    return re.sub(r"s$", "", value.casefold())


def _extended_shift(value: datetime, amount: float, unit: str) -> datetime:
    if unit in {"second", "minute", "hour", "day", "week"}:
        seconds = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
            "week": 604800,
        }[unit]
        return value + timedelta(seconds=amount * seconds)
    months = amount * (3 if unit == "quarter" else 12 if unit == "year" else 1)
    target_date = _add_months(value.date(), int(months))
    return datetime.combine(target_date, value.timetz())


def _extended_date_at(value: datetime, amount: float, unit: str, timezone: tzinfo) -> datetime:
    if unit in {"second", "minute", "hour"}:
        return _extended_shift(value, amount, unit)
    target = _extended_shift(value, amount, unit)
    return datetime.combine(target.date(), time.min, tzinfo=timezone)


def _part_of_day_time(value: date, label: str, timezone: tzinfo) -> datetime:
    hours = {
        "morning": 9,
        "afternoon": 14,
        "evening": 18,
        "night": 21,
    }
    return datetime.combine(value, time(hours.get(label, 12), tzinfo=timezone))


def _quarter_bounds(reference: date, year: int, quarter: int) -> tuple[date, date]:
    quarter = max(1, min(4, quarter))
    start = date(year, 3 * quarter - 2, 1)
    end = _add_months(start, 3) - timedelta(days=1)
    return start, end


def _extended_period_bounds(reference: date, unit: str, direction: str) -> tuple[date, date, str]:
    direction_map = {
        "last": -1,
        "previous": -1,
        "this": 0,
        "next": 1,
        "following": 1,
        "upcoming": 1,
        "coming": 1,
    }
    offset = direction_map.get(direction, 0)
    if unit == "week":
        start = reference - timedelta(days=reference.weekday())
        start += timedelta(weeks=offset)
        return start, start + timedelta(days=6), "week"
    if unit == "month":
        start = _add_months(reference.replace(day=1), offset)
        return start, _add_months(start, 1) - timedelta(days=1), "month"
    if unit == "quarter":
        quarter = (reference.month - 1) // 3
        start = _add_months(reference.replace(day=1), (quarter + offset) * 3)
        return start, _add_months(start, 3) - timedelta(days=1), "quarter"
    if unit == "year":
        start = date(reference.year + offset, 1, 1)
        return start, date(start.year, 12, 31), "year"
    raise ValueError(f"Unsupported temporal period: {unit}")


def _extended_interval_match(
    expression: str,
    reference: datetime,
    timezone: tzinfo,
) -> TemporalMatch | None:
    candidate = re.sub(r"\s+", " ", expression.strip())
    if re.fullmatch(
        r"(?:the\s+)?(?:last|this|next|previous|following|upcoming|coming)\s+(?:week|month|quarter|year|weekend)",
        candidate,
        re.IGNORECASE,
    ):
        return None
    prefix_match = re.fullmatch(
        rf"(?P<prefix>over|throughout|during|for|within|in)?\s*(?:the\s+)?"
        rf"(?P<direction>past|last|previous|next|following|upcoming|coming)"
        rf"(?:\s+(?P<count>{_EXTENDED_COUNT_PATTERN}))?\s+"
        rf"(?P<unit>{_EXTENDED_UNIT_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if prefix_match is not None:
        count_value = _extended_number(prefix_match.group("count") or "one") or 1
        count = max(1, round(count_value))
        unit = _extended_unit(prefix_match.group("unit"))
        direction = prefix_match.group("direction").casefold()
        prefix = (prefix_match.group("prefix") or "").casefold()
        if direction == "past":
            start = _extended_date_at(reference, -(count - 1), unit, timezone)
            end = _extended_date_at(reference, 0, unit, timezone)
        elif direction in {"last", "previous"}:
            start = _extended_date_at(reference, -count, unit, timezone)
            end = _extended_date_at(reference, -1, unit, timezone)
        else:
            start_offset = 0 if prefix in {"over", "throughout", "during", "within", "in"} else 1
            start = _extended_date_at(reference, start_offset, unit, timezone)
            end = _extended_date_at(reference, count, unit, timezone)
        return _resolved_match(candidate, start, end, unit, timezone, "relative_expression")

    duration_match = re.fullmatch(
        rf"(?:for|over|throughout|during|within)\s+(?:the\s+)?"
        rf"(?P<count>{_EXTENDED_COUNT_PATTERN})\s+(?P<unit>{_EXTENDED_UNIT_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if duration_match is not None:
        count = max(1, round(_extended_number(duration_match.group("count")) or 1))
        unit = _extended_unit(duration_match.group("unit"))
        start = reference
        end = _extended_date_at(reference, count, unit, timezone)
        return _resolved_match(candidate, start, end, unit, timezone, "relative_expression")

    return None


def _extended_endpoint(
    expression: str,
    reference: datetime,
    timezone: tzinfo,
) -> TemporalMatch | None:
    candidate = re.sub(r"^(?:on|at)\s+", "", expression.strip().rstrip(".,!?;:"), flags=re.IGNORECASE)
    exact = _parse_exact_value(candidate, timezone)
    if exact is not None:
        return exact
    year_match = re.fullmatch(r"(?:in\s+)?(?P<year>\d{4})", candidate, re.IGNORECASE)
    if year_match is not None:
        year = int(year_match.group("year"))
        return _resolved_date_match(candidate, date(year, 1, 1), date(year, 12, 31), "year", timezone, "explicit_date")
    current = _resolve_match(candidate, reference, timezone)
    if current is not None:
        return current
    resolved = _resolve_additional_expression(candidate, reference, timezone, allow_interval=False)
    if resolved is not None and resolved.event_start is not None:
        return resolved
    time_match = re.fullmatch(
        rf"(?:at\s+)?(?P<time>{_TIME_PATTERN}|noon|midnight)",
        candidate,
        re.IGNORECASE,
    )
    if time_match is not None:
        time_text = time_match.group("time").casefold()
        if time_text == "noon":
            target = datetime.combine(reference.date(), time(12), tzinfo=timezone)
        elif time_text == "midnight":
            target = datetime.combine(reference.date(), time(0), tzinfo=timezone)
        else:
            target = _parse_time_expression(time_match.group("time"), reference.date(), timezone)
        if target is not None:
            return _resolved_match(candidate, target, None, "exact", timezone, "relative_expression")
    return None


def _split_extended_interval(expression: str) -> tuple[str, str] | None:
    candidate = re.sub(r"^(?:from|between)\s+", "", expression.strip(), flags=re.IGNORECASE)
    word_match = re.search(r"\s+(?:to|through|until|and)\s+", candidate, re.IGNORECASE)
    if word_match is not None:
        return (
            candidate[:word_match.start()].strip().rstrip(".,!?;:"),
            candidate[word_match.end():].strip().rstrip(".,!?;:"),
        )
    single_dash_match = re.fullmatch(
        rf"(?P<start>{_EXTENDED_BARE_START_PATTERN})\s*-\s*(?P<end>{_EXTENDED_BARE_START_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if single_dash_match is not None:
        return single_dash_match.group("start").strip(), single_dash_match.group("end").strip()
    dash_match = re.fullmatch(
        r"(?P<start>.+?)\s*(?:--|–|—|\s-\s)\s*(?P<end>[A-Za-z0-9].*)",
        candidate,
        re.IGNORECASE,
    )
    if dash_match is not None:
        return dash_match.group("start").strip().rstrip(".,!?;:"), dash_match.group("end").strip().rstrip(".,!?;:")
    return None


def _resolve_extended_interval(
    expression: str,
    reference: datetime,
    timezone: tzinfo,
) -> TemporalMatch | None:
    existing = _resolve_interval(expression, reference, timezone)
    if existing is not None:
        return existing
    split = _split_extended_interval(expression)
    if split is None:
        return None
    start_expression, end_expression = split
    left = _extended_endpoint(start_expression, reference, timezone)
    right = _extended_endpoint(end_expression, reference, timezone)
    if left is None or right is None or left.event_start is None or right.event_start is None:
        return None
    start = left.event_start
    end = right.event_end or right.event_start
    bare_weekday = re.fullmatch(
        rf"(?:the\s+)?(?P<weekday>{_WEEKDAY_PATTERN})",
        end_expression.strip(),
        re.IGNORECASE,
    )
    if bare_weekday is not None and end < start:
        weekday = _WEEKDAYS[bare_weekday.group("weekday").casefold()]
        if left.temporal_precision == "week":
            target_date = start.date() + timedelta(days=weekday)
        else:
            target_date = start.date() + timedelta(days=(weekday - start.weekday()) % 7)
        end = _date_at(target_date, timezone)
    if end < start:
        return None
    basis = (
        "relative_expression"
        if left.temporal_basis == "relative_expression" or right.temporal_basis == "relative_expression"
        else "explicit_date"
    )
    return _resolved_match(expression, start, end, _interval_precision(left, right), timezone, basis)


def _resolve_additional_expression(
    expression: str,
    reference: datetime | None,
    timezone: tzinfo,
    *,
    allow_interval: bool = True,
) -> TemporalMatch | None:
    if reference is None:
        return None
    candidate = re.sub(r"^(?:on|around|about|approximately)\s+", "", expression.strip(), flags=re.IGNORECASE)
    candidate = re.sub(r"\s+", " ", candidate)
    if re.fullmatch(r"(?:the\s+)?week\s+before\s+next\s+month", candidate, re.IGNORECASE):
        return None
    local_reference = reference.astimezone(timezone)
    reference_date = local_reference.date()

    until_match = re.fullmatch(r"(?:until|by)\s+(?P<target>.+)", candidate, re.IGNORECASE)
    if until_match is not None:
        target = _extended_endpoint(until_match.group("target"), local_reference, timezone)
        if target is not None and target.event_start is not None:
            if target.temporal_precision in {"day", "week", "month", "quarter", "year"}:
                start = _date_at(reference_date, timezone)
            else:
                start = local_reference
            end = target.event_end or target.event_start
            if end >= start:
                return _resolved_match(expression, start, end, target.temporal_precision, timezone, "relative_expression")

    if allow_interval:
        interval = _resolve_extended_interval(candidate, local_reference, timezone)
        if interval is not None:
            return interval
        interval = _extended_interval_match(candidate, local_reference, timezone)
        if interval is not None:
            return interval

    if re.fullmatch(r"(?:right\s+now|just\s+now|now|at\s+this\s+time|right\s+then|at\s+the\s+moment)", candidate, re.IGNORECASE):
        return _resolved_match(expression, local_reference, None, "exact", timezone, "relative_expression")
    if re.fullmatch(r"tonight", candidate, re.IGNORECASE):
        return _resolved_match(
            expression,
            _part_of_day_time(reference_date, "night", timezone),
            None,
            "day",
            timezone,
            "relative_expression",
        )
    if re.fullmatch(r"noon|midnight", candidate, re.IGNORECASE):
        target_hour = 12 if candidate.casefold() == "noon" else 0
        return _resolved_match(
            expression,
            datetime.combine(reference_date, time(target_hour), tzinfo=timezone),
            None,
            "exact",
            timezone,
            "relative_expression",
        )

    timed_day = re.fullmatch(
        rf"(?P<day>today|tonight|tomorrow|yesterday)\s+(?:at\s+)?"
        rf"(?P<part>morning|afternoon|evening|night|noon|midnight|{_TIME_PATTERN})",
        candidate,
        re.IGNORECASE,
    )
    if timed_day is not None:
        day_value = timed_day.group("day").casefold()
        day_offset = {"yesterday": -1, "today": 0, "tonight": 0, "tomorrow": 1}[day_value]
        target_date = reference_date + timedelta(days=day_offset)
        part = timed_day.group("part")
        if part.casefold() in {"morning", "afternoon", "evening", "night"}:
            target = _part_of_day_time(target_date, part.casefold(), timezone)
            precision = "day"
        elif part.casefold() == "noon":
            target = datetime.combine(target_date, time(12), tzinfo=timezone)
            precision = "exact"
        elif part.casefold() == "midnight":
            target = datetime.combine(target_date, time(0), tzinfo=timezone)
            precision = "exact"
        else:
            target = _parse_time_expression(part, target_date, timezone)
            precision = "exact"
        if target is not None:
            return _resolved_match(expression, target, None, precision, timezone, "relative_expression")

    week_of = re.fullmatch(
        r"(?:the\s+)?(?P<unit>week|month|quarter)\s+of\s+(?P<target>.+)",
        candidate,
        re.IGNORECASE,
    )
    if week_of is not None:
        target = _extended_endpoint(week_of.group("target"), local_reference, timezone)
        if target is not None and target.event_start is not None:
            unit = week_of.group("unit").casefold()
            target_date = target.event_start.date()
            if unit == "week":
                start_date = target_date - timedelta(days=target_date.weekday())
                end_date = start_date + timedelta(days=6)
                precision = "week"
            elif unit == "month":
                start_date = target_date.replace(day=1)
                end_date = _add_months(start_date, 1) - timedelta(days=1)
                precision = "month"
            else:
                quarter = (target_date.month - 1) // 3
                start_date = _add_months(target_date.replace(day=1), quarter * 3)
                end_date = _add_months(start_date, 3) - timedelta(days=1)
                precision = "quarter"
            return _resolved_match(
                expression,
                _date_at(start_date, timezone),
                _date_at(end_date, timezone),
                precision,
                timezone,
                target.temporal_basis,
            )

    relative_week = re.fullmatch(
        r"(?:the\s+)?week\s+(?P<direction>before|after)\s+"
        r"(?P<target>last|this|next|previous|following|upcoming)(?:\s+(?P<unit>week|month|quarter|year))?",
        candidate,
        re.IGNORECASE,
    )
    if relative_week is not None:
        target_unit = relative_week.group("unit") or "week"
        target_direction = relative_week.group("target").casefold()
        target_start, target_end, _ = _extended_period_bounds(
            reference_date,
            target_unit,
            target_direction,
        )
        if relative_week.group("direction").casefold() == "before":
            start_date = target_start - timedelta(days=7)
        else:
            start_date = target_end + timedelta(days=1)
        return _resolved_match(
            expression,
            _date_at(start_date, timezone),
            _date_at(start_date + timedelta(days=6), timezone),
            "week",
            timezone,
            "relative_expression",
        )

    part_period = re.fullmatch(
        r"(?P<direction>last|this|next|previous|following|upcoming)\s+"
        r"(?P<part>morning|afternoon|evening|night)",
        candidate,
        re.IGNORECASE,
    )
    if part_period is not None:
        direction = part_period.group("direction").casefold()
        offset = -1 if direction in {"last", "previous"} else 1 if direction in {"next", "following", "upcoming"} else 0
        target_date = reference_date + timedelta(days=offset)
        target = _part_of_day_time(target_date, part_period.group("part").casefold(), timezone)
        return _resolved_match(expression, target, None, "day", timezone, "relative_expression")

    day_phrase = re.fullmatch(
        r"(?:the\s+)?day\s+(?P<direction>before\s+yesterday|after\s+tomorrow)",
        candidate,
        re.IGNORECASE,
    )
    if day_phrase is not None:
        amount = -2 if day_phrase.group("direction").casefold().startswith("before") else 2
        return _resolved_date_match(expression, reference_date + timedelta(days=amount), None, "day", timezone, "relative_expression")

    period_match = re.fullmatch(
        r"(?:the\s+)?(?P<direction>last|this|next|previous|following|upcoming|coming)\s+"
        r"(?P<unit>week|month|quarter|year|weekend)",
        candidate,
        re.IGNORECASE,
    )
    if period_match is not None:
        unit = period_match.group("unit").casefold()
        direction = period_match.group("direction").casefold()
        if unit == "weekend":
            start = reference_date - timedelta(days=reference_date.weekday() + (2 if reference_date.weekday() < 5 else 0))
            if direction in {"last", "previous"}:
                start -= timedelta(days=7)
            elif direction in {"next", "following", "upcoming", "coming"}:
                start += timedelta(days=7 if reference_date.weekday() < 5 else 0)
            end = start + timedelta(days=1)
            return _resolved_match(expression, _date_at(start, timezone), _date_at(end, timezone), "week", timezone, "relative_expression")
        start, end, precision = _extended_period_bounds(reference_date, unit, direction)
        return _resolved_match(expression, _date_at(start, timezone), _date_at(end, timezone), precision, timezone, "relative_expression")

    weekday_match = re.fullmatch(
        r"(?:the\s+)?(?P<direction>last|this|next|previous|following|upcoming)?\s*"
        r"(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"(?:\s+(?:at\s+)?(?P<time>{_TIME_PATTERN}))?",
        candidate,
        re.IGNORECASE,
    )
    if weekday_match is not None:
        direction = (weekday_match.group("direction") or "this").casefold()
        weekday = _WEEKDAYS[weekday_match.group("weekday").casefold()]
        current_week = reference_date - timedelta(days=reference_date.weekday())
        if direction in {"last", "previous"}:
            days_since = (reference_date.weekday() - weekday) % 7 or 7
            target_date = reference_date - timedelta(days=days_since)
        elif direction == "this":
            target_date = current_week + timedelta(days=weekday)
        else:
            target_date = current_week + timedelta(days=7 + weekday)
        time_text = weekday_match.group("time")
        if time_text is not None:
            target = _parse_time_expression(time_text, target_date, timezone)
            precision = "exact"
        else:
            target = _date_at(target_date, timezone)
            precision = "day"
        if target is not None:
            return _resolved_match(expression, target, None, precision, timezone, "relative_expression")

    ordinal_quarter = re.fullmatch(
        r"(?:the\s+)?(?P<ordinal>first|second|third|fourth)\s+quarter\s+of\s+(?P<year>\d{4})",
        candidate,
        re.IGNORECASE,
    )
    if ordinal_quarter is not None:
        quarter = {"first": 1, "second": 2, "third": 3, "fourth": 4}[ordinal_quarter.group("ordinal").casefold()]
        year = int(ordinal_quarter.group("year"))
        start, end = _quarter_bounds(reference_date, year, quarter)
        return _resolved_match(expression, _date_at(start, timezone), _date_at(end, timezone), "quarter", timezone, "explicit_date")

    quarter_match = re.fullmatch(
        r"(?:q(?P<quarter>[1-4])\s+(?P<year>\d{4})|(?P<year2>\d{4})\s+q(?P<quarter2>[1-4]))",
        candidate,
        re.IGNORECASE,
    )
    if quarter_match is not None:
        year = int(quarter_match.group("year") or quarter_match.group("year2"))
        quarter = int(quarter_match.group("quarter") or quarter_match.group("quarter2"))
        start, end = _quarter_bounds(reference_date, year, quarter)
        return _resolved_match(expression, _date_at(start, timezone), _date_at(end, timezone), "quarter", timezone, "explicit_date")

    relative_point = re.fullmatch(
        rf"(?:(?P<prefix>in|after|before)\s+)?(?:the\s+)?(?P<count>{_EXTENDED_COUNT_PATTERN})\s+"
        rf"(?P<unit>{_EXTENDED_UNIT_PATTERN})(?:\s+(?P<suffix>ago|later|hence|from\s+now|from\s+today|before\s+now|after\s+now))?",
        candidate,
        re.IGNORECASE,
    )
    if relative_point is not None:
        prefix = (relative_point.group("prefix") or "").casefold()
        suffix = (relative_point.group("suffix") or "").casefold()
        if not prefix and not suffix:
            return None
        count = _extended_number(relative_point.group("count")) or 1
        unit = _extended_unit(relative_point.group("unit"))
        if suffix in {"ago", "before now"} or prefix == "before":
            amount = -count
        elif suffix in {"later", "hence", "from now", "from today", "after now"} or prefix in {"in", "after"}:
            amount = count
        else:
            amount = count
        if unit in {"second", "minute", "hour"}:
            target = _extended_shift(local_reference, amount, unit)
            precision = unit
        else:
            target = _extended_date_at(local_reference, amount, unit, timezone)
            precision = unit
        return _resolved_match(expression, target, None, precision, timezone, "relative_expression")

    return None


def _iter_expression_spans(text: str) -> list[tuple[int, int, str]]:
    candidates: list[tuple[int, int, str, int]] = []
    patterns = (
        (_EXTENDED_INTERVAL_RE, -2),
        (_EXTENDED_DASH_INTERVAL_RE, -2),
        (_EXTENDED_SPAN_RE, -1),
        (_INTERVAL_RE, 0),
        (_SHORT_DAY_RANGE_RE, 1),
        (_ISO_DATETIME_RE, 2),
        (_NATURAL_DATETIME_RE, 3),
        (_EXTRA_RELATIVE_RE, 4),
        (_EXPRESSION_RE, 5),
    )
    for pattern, priority in patterns:
        for found in pattern.finditer(text):
            groups = found.groupdict()
            expression = (
                groups.get("interval")
                or groups.get("short_range")
                or groups.get("iso_datetime")
                or groups.get("natural_datetime")
                or groups.get("extra_expression")
                or groups.get("extended_expression")
                or found.group(0)
            )
            candidates.append((found.start(), found.end(), expression, priority))
    candidates.sort(key=lambda value: (value[0], -(value[1] - value[0]), value[3]))
    selected: list[tuple[int, int, str]] = []
    cursor = -1
    for start, end, expression, _ in candidates:
        if start < cursor:
            continue
        selected.append((start, end, expression))
        cursor = end
    return selected


def _attach_source_span(
    match: TemporalMatch,
    source_start: int | None,
    source_end: int | None,
) -> TemporalMatch:
    if source_start is not None:
        match.source_start = source_start
    if source_end is not None:
        match.source_end = source_end
    if source_start is not None and source_end is not None:
        match.source_span = {"start": source_start, "end": source_end}
    return match


def _resolve_week_before(expression: str, timezone: tzinfo) -> TemporalMatch | None:
    target_match = re.fullmatch(r"week\s+before\s+(.+)", expression.strip(), re.IGNORECASE)
    if target_match is None:
        return None
    parsed = _parse_absolute_expression(target_match.group(1))
    if parsed is None or parsed[2] != "day":
        return None
    try:
        target = parsed[0] - timedelta(days=7)
    except OverflowError:
        return None
    return _resolved_date_match(expression, target, None, "day", timezone, "relative_expression")


def _period_bounds(reference: date, unit: str, offset: int) -> tuple[date, date, str]:
    if unit == "week":
        start = reference - timedelta(days=reference.weekday())
        start += timedelta(weeks=offset)
        return start, start + timedelta(days=6), "week"
    if unit == "month":
        first = reference.replace(day=1)
        start = _add_months(first, offset)
        next_month = _add_months(start, 1)
        return start, next_month - timedelta(days=1), "month"
    if unit == "year":
        start = date(reference.year + offset, 1, 1)
        return start, date(start.year, 12, 31), "year"
    raise ValueError(f"Unsupported temporal period: {unit}")


def _unresolved(
    expression: str,
    basis: str = "unresolved_no_reference",
    timezone: tzinfo | None = None,
) -> TemporalMatch:
    return TemporalMatch(
        original_expression=expression,
        normalized_expression=expression,
        temporal_precision="unknown",
        temporal_basis=basis,
        timezone=str(timezone) if timezone is not None else None,
    )


def _resolve_explicit_without_reference(expression: str, timezone: tzinfo) -> TemporalMatch | None:
    extra = _resolve_extra_expression(expression, None, timezone)
    if extra is not None and extra.resolved_at is not None:
        return extra
    ordinal_quarter = re.fullmatch(
        r"(?:the\s+)?(?P<ordinal>first|second|third|fourth)\s+quarter\s+of\s+(?P<year>\d{4})",
        expression.strip(),
        re.IGNORECASE,
    )
    if ordinal_quarter is not None:
        quarter = {"first": 1, "second": 2, "third": 3, "fourth": 4}[ordinal_quarter.group("ordinal").casefold()]
        year = int(ordinal_quarter.group("year"))
        start, end = _quarter_bounds(date(year, 1, 1), year, quarter)
        return _resolved_date_match(expression, start, end, "quarter", timezone, "explicit_date")
    quarter_match = re.fullmatch(
        r"(?:q(?P<quarter>[1-4])\s+(?P<year>\d{4})|(?P<year2>\d{4})\s+q(?P<quarter2>[1-4]))",
        expression.strip(),
        re.IGNORECASE,
    )
    if quarter_match is not None:
        year = int(quarter_match.group("year") or quarter_match.group("year2"))
        quarter = int(quarter_match.group("quarter") or quarter_match.group("quarter2"))
        start, end = _quarter_bounds(date(year, 1, 1), year, quarter)
        return _resolved_date_match(expression, start, end, "quarter", timezone, "explicit_date")
    match = _EXPRESSION_RE.fullmatch(expression.strip())
    if match is None:
        return None
    original = match.group(0)
    if match.group("week_before"):
        return _resolve_week_before(original, timezone)
    if any(
        match.group(group_name)
        for group_name in ("explicit_date", "explicit_slash_date", "natural_date", "year_only")
    ):
        return _resolve_explicit_match(original, timezone)
    return None


def _resolve_match(expression: str, reference: datetime, timezone: tzinfo) -> TemporalMatch | None:
    match = _EXPRESSION_RE.fullmatch(expression.strip())
    if match is None:
        return None

    original = match.group(0)
    groups = match.groupdict()
    local_reference = reference.astimezone(timezone)
    reference_date = local_reference.date()

    if groups["week_before"]:
        return (
            _resolve_week_before(original, timezone)
            or _resolve_extra_expression(original, reference, timezone)
            or _unresolved(original, "unresolved_unknown_expression", timezone)
        )

    if groups["day_word"]:
        offsets = {"yesterday": -1, "today": 0, "tomorrow": 1}
        target = reference_date + timedelta(days=offsets[groups["day_word"].lower()])
        return TemporalMatch(
            original_expression=original,
            normalized_expression=target.isoformat(),
            resolved_at=_date_at(target, timezone),
            temporal_precision="day",
            temporal_basis="relative_expression",
        )

    if groups["period_direction"]:
        direction = groups["period_direction"].lower()
        offset = {"last": -1, "this": 0, "next": 1}[direction]
        start, end, precision = _period_bounds(reference_date, groups["period_unit"].lower(), offset)
        return TemporalMatch(
            original_expression=original,
            normalized_expression=f"{start.isoformat()} through {end.isoformat()}",
            resolved_at=_date_at(start, timezone),
            end_at=_date_at(end, timezone),
            temporal_precision=precision,
            temporal_basis="relative_expression",
        )

    if groups["weekday_direction"]:
        direction = groups["weekday_direction"].lower()
        weekday = _WEEKDAYS[groups["weekday_name"].lower()]
        current_week = reference_date - timedelta(days=reference_date.weekday())
        if direction == "last":
            days_since = (reference_date.weekday() - weekday) % 7
            if days_since == 0:
                days_since = 7
            target = reference_date - timedelta(days=days_since)
        elif direction == "this":
            target = current_week + timedelta(days=weekday)
        else:
            target = current_week + timedelta(days=7 + weekday)
        return TemporalMatch(
            original_expression=original,
            normalized_expression=target.isoformat(),
            resolved_at=_date_at(target, timezone),
            temporal_precision="day",
            temporal_basis="relative_expression",
        )

    if groups["ago_count"]:
        raw_count = groups["ago_count"].lower()
        count = _NUMBER_WORDS.get(raw_count, int(raw_count) if raw_count.isdigit() else 0)
        unit = groups["ago_unit"].lower()
        if unit in {"day", "week"}:
            target = reference_date - timedelta(days=count * (1 if unit == "day" else 7))
        elif unit == "month":
            target = _add_months(reference_date, -count)
        else:
            target = _add_months(reference_date, -count * 12)
        return TemporalMatch(
            original_expression=original,
            normalized_expression=target.isoformat(),
            resolved_at=_date_at(target, timezone),
            temporal_precision=unit,
            temporal_basis="relative_expression",
        )

    if groups["weekday_only"]:
        weekday = _WEEKDAYS[groups["weekday_only"].lower()]
        days_until = (weekday - reference_date.weekday()) % 7
        target = reference_date + timedelta(days=days_until)
        return TemporalMatch(
            original_expression=original,
            normalized_expression=target.isoformat(),
            resolved_at=_date_at(target, timezone),
            temporal_precision="day",
            temporal_basis="relative_expression",
        )

    if groups["explicit_date"] or groups["explicit_slash_date"]:
        explicit_value = groups["explicit_date"] or groups["explicit_slash_date"]
        try:
            target = (
                date.fromisoformat(explicit_value)
                if "-" in explicit_value
                else date(*(int(part) for part in explicit_value.split("/")))
            )
        except ValueError:
            return None
        return TemporalMatch(
            original_expression=original,
            normalized_expression=target.isoformat(),
            resolved_at=_date_at(target, timezone),
            temporal_precision="day",
            temporal_basis="explicit_date",
        )

    if groups["natural_date"] or groups["year_only"]:
        return _resolve_explicit_match(original, timezone)

    return None


def normalize_temporal_expression(
    expression: str,
    reference_at: DateInput = None,
    timezone: TimezoneInput = None,
    *,
    reference_datetime: DateInput = None,
    reference_date: DateInput = None,
) -> TemporalMatch:
    selected_reference = reference_datetime if reference_datetime is not None else reference_date
    if selected_reference is None:
        selected_reference = reference_at
    selected_timezone = _coerce_timezone(timezone, selected_reference)
    reference = _coerce_datetime(selected_reference, selected_timezone)
    if reference is None:
        explicit = _resolve_explicit_without_reference(str(expression), selected_timezone)
        return explicit or _unresolved(str(expression), timezone=selected_timezone)
    resolved = _resolve_extra_expression(str(expression), reference, selected_timezone)
    if resolved is None:
        resolved = _resolve_match(str(expression), reference, selected_timezone)
    if resolved is None:
        return _unresolved(str(expression), "unresolved_unknown_expression", selected_timezone)
    if resolved.timezone is None:
        resolved.timezone = str(selected_timezone)
    return resolved


def resolve_temporal_expression(
    expression: str,
    reference_at: DateInput = None,
    timezone: TimezoneInput = None,
    *,
    reference_datetime: DateInput = None,
    reference_date: DateInput = None,
) -> TemporalMatch:
    return normalize_temporal_expression(
        expression,
        reference_at,
        timezone,
        reference_datetime=reference_datetime,
        reference_date=reference_date,
    )


def normalize_temporal_text(
    text: str,
    reference_at: DateInput = None,
    timezone: TimezoneInput = None,
    *,
    reference_datetime: DateInput = None,
    reference_date: DateInput = None,
) -> TemporalText:
    selected_reference = reference_datetime if reference_datetime is not None else reference_date
    if selected_reference is None:
        selected_reference = reference_at
    selected_timezone = _coerce_timezone(timezone, selected_reference)
    reference = _coerce_datetime(selected_reference, selected_timezone)
    original_text = str(text)
    pieces: list[str] = []
    matches: list[TemporalMatch] = []
    cursor = 0
    for source_start, source_end, expression in _iter_expression_spans(original_text):
        if reference is None:
            resolved = _resolve_explicit_without_reference(expression, selected_timezone)
        else:
            resolved = _resolve_extra_expression(expression, reference, selected_timezone)
            if resolved is None:
                resolved = _resolve_match(expression, reference, selected_timezone)
        if resolved is None:
            resolved = _unresolved(
                expression,
                "unresolved_no_reference" if reference is None else "unresolved_unknown_expression",
                selected_timezone,
            )
        if resolved.timezone is None:
            resolved.timezone = str(selected_timezone)
        _attach_source_span(resolved, source_start, source_end)
        pieces.append(original_text[cursor:source_start])
        pieces.append(resolved.normalized_expression)
        cursor = source_end
        matches.append(resolved)
    pieces.append(original_text[cursor:])
    resolved_match = next((match for match in matches if match.event_start is not None), None)
    return TemporalText(
        original_text=original_text,
        normalized_text="".join(pieces),
        reference_at=reference,
        event_start=resolved_match.event_start if resolved_match is not None else None,
        event_end=resolved_match.event_end if resolved_match is not None else None,
        temporal_precision=resolved_match.temporal_precision if resolved_match is not None else "unknown",
        temporal_basis=(
            resolved_match.temporal_basis
            if resolved_match is not None
            else "unresolved_no_reference"
            if reference is None
            else "unresolved_unknown_expression"
        ),
        timezone=str(selected_timezone),
        source_start=resolved_match.source_span.get("start") if resolved_match is not None and resolved_match.source_span else None,
        source_end=resolved_match.source_span.get("end") if resolved_match is not None and resolved_match.source_span else None,
        source_spans=[match.source_span for match in matches if match.source_span is not None],
        matches=matches,
    )


class TemporalNormalizer:
    def __init__(
        self,
        reference_at: DateInput = None,
        timezone: TimezoneInput = None,
        *,
        reference_datetime: DateInput = None,
        reference_date: DateInput = None,
    ) -> None:
        selected_reference = reference_datetime if reference_datetime is not None else reference_date
        if selected_reference is None:
            selected_reference = reference_at
        self._timezone = _coerce_timezone(timezone, selected_reference)
        self._reference = _coerce_datetime(selected_reference, self._timezone)

    @property
    def reference_at(self) -> datetime | None:
        return self._reference

    @property
    def timezone(self) -> tzinfo:
        return self._timezone

    def normalize(self, expression: str) -> TemporalMatch:
        return normalize_temporal_expression(expression, self._reference, self._timezone)

    def normalize_text(self, text: str) -> TemporalText:
        return normalize_temporal_text(text, self._reference, self._timezone)


def _string_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _message_text_value(message: Mapping[str, Any], key: str) -> str | None:
    value = message.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts: list[str] = []
        for block in value:
            if isinstance(block, Mapping):
                candidate = block.get("text") or block.get("content")
            else:
                candidate = block
            if isinstance(candidate, str):
                parts.append(candidate)
        return "\n".join(parts) if parts else None
    return None


def _message_text_keys(message: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(key for key in ("content", "text") if _message_text_value(message, key) is not None)


def _message_text_key(message: Mapping[str, Any]) -> str | None:
    keys = _message_text_keys(message)
    return keys[0] if keys else None


def normalize_temporal_messages(
    messages: Sequence[Mapping[str, Any]],
    *,
    occurred_at: DateInput = None,
    observed_at: DateInput = None,
    source_id: Any = None,
    message_id: Any = None,
    timezone: TimezoneInput = None,
) -> list[dict[str, Any]]:
    normalized_messages: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        item = dict(message)
        message_occurred = item.get("occurred_at")
        message_observed = item.get("observed_at")
        message_timezone = item.get("timezone") or item.get("source_timezone") or timezone
        timezone_reference = (
            message_occurred
            if message_occurred is not None
            else message_observed
            if message_observed is not None
            else occurred_at
            if occurred_at is not None
            else observed_at
        )
        try:
            selected_timezone = _coerce_timezone(message_timezone, timezone_reference)
        except ValueError:
            try:
                selected_timezone = _coerce_timezone(None, timezone_reference)
            except ValueError:
                selected_timezone = UTC
        parsed_occurred = _coerce_datetime(message_occurred, selected_timezone)
        parsed_observed = _coerce_datetime(message_observed, selected_timezone)
        fallback_occurred = _coerce_datetime(occurred_at, selected_timezone)
        fallback_observed = _coerce_datetime(observed_at, selected_timezone)
        resolved_occurred = parsed_occurred or fallback_occurred
        resolved_observed = parsed_observed or fallback_observed
        explicit_event_start = _coerce_datetime(item.get("event_start"), selected_timezone)
        explicit_event_at = _coerce_datetime(item.get("event_at"), selected_timezone)
        reference = resolved_occurred or resolved_observed or explicit_event_start or explicit_event_at
        text_values = {key: _message_text_value(item, key) for key in _message_text_keys(item)}
        normalized_texts = {
            key: normalize_temporal_text(text_values[key] or "", reference, selected_timezone)
            for key in text_values
        }
        original_texts = {key: text_values[key] or "" for key in normalized_texts}
        for key, normalized_text in normalized_texts.items():
            original_value = original_texts[key]
            item.setdefault(f"original_{key}", original_value)
            item.setdefault(f"normalized_{key}", normalized_text.normalized_text)
            item[key] = normalized_text.normalized_text
        primary_key = "content" if "content" in normalized_texts else "text" if "text" in normalized_texts else None
        primary_text = normalized_texts.get(primary_key) if primary_key is not None else None
        primary_original = original_texts.get(primary_key) if primary_key is not None else None
        supplied_original = item.get("original_text")
        if isinstance(supplied_original, str) and supplied_original:
            primary_original = supplied_original
        if primary_original is not None:
            item.setdefault("original_text", primary_original)
            item.setdefault("normalized_text", primary_text.normalized_text if primary_text is not None else primary_original)
        if (
            "content" in normalized_texts
            and "text" not in item
            and (reference is not None or normalized_texts["content"].resolved)
        ):
            item["text"] = normalized_texts["content"].normalized_text
            item.setdefault("original_text_alias", original_texts["content"])
            item.setdefault("normalized_text_alias", normalized_texts["content"].normalized_text)
        if resolved_occurred is not None:
            item["occurred_at"] = resolved_occurred.isoformat()
        if resolved_observed is not None:
            item["observed_at"] = resolved_observed.isoformat()
        source = _string_id(item.get("source_id") or source_id)
        current_message_id = _string_id(item.get("message_id") or item.get("source_message_id") or message_id)
        explicit_event_end = _coerce_datetime(item.get("event_end"), selected_timezone)
        all_matches = [
            match
            for normalized_text in normalized_texts.values()
            for match in normalized_text.matches
        ]
        event_start = explicit_event_start or explicit_event_at or (primary_text.event_start if primary_text is not None else None) or reference
        event_end = explicit_event_end or (primary_text.event_end if primary_text is not None else None)
        source_span = item.get("source_span") if isinstance(item.get("source_span"), Mapping) else None
        if source_span is None and primary_text is not None:
            source_span = primary_text.source_span
        temporal_basis = str(item.get("temporal_basis") or "")
        if not temporal_basis:
            temporal_basis = (
                "message_occurred_at"
                if parsed_occurred is not None
                else "payload_occurred_at"
                if fallback_occurred is not None
                else "message_observed_at"
                if parsed_observed is not None
                else "payload_observed_at"
                if fallback_observed is not None
                else primary_text.temporal_basis
                if primary_text is not None and primary_text.temporal_basis != "unresolved_unknown_expression"
                else "unavailable"
            )
        temporal_precision = item.get("temporal_precision")
        if not temporal_precision:
            temporal_precision = primary_text.temporal_precision if primary_text is not None else "exact" if reference is not None else "unknown"
        context = TemporalMessageContext(
            reference_at=reference,
            occurred_at=resolved_occurred,
            observed_at=resolved_observed,
            event_start=event_start,
            event_end=event_end,
            source_id=source,
            message_id=current_message_id,
            timezone=str(selected_timezone),
            temporal_precision=str(temporal_precision),
            temporal_basis=temporal_basis,
            source_start=source_span.get("start") if source_span else item.get("source_start"),
            source_end=source_span.get("end") if source_span else item.get("source_end"),
            source_span=dict(source_span) if source_span else None,
            matches=all_matches,
            original_text=primary_original,
            normalized_text=primary_text.normalized_text if primary_text is not None else None,
        )
        item["event_at"] = context.event_start.isoformat() if context.event_start is not None else None
        item["event_start"] = context.event_start.isoformat() if context.event_start is not None else None
        item["event_end"] = context.event_end.isoformat() if context.event_end is not None else None
        item["timezone"] = context.timezone
        item["temporal_precision"] = context.temporal_precision
        item["temporal_basis"] = context.temporal_basis
        if context.source_span is not None:
            item["source_span"] = context.source_span
        if (
            context.reference_at is not None
            or context.source_id is not None
            or context.message_id is not None
            or context.event_start is not None
            or any(normalized_text.resolved for normalized_text in normalized_texts.values())
        ):
            item["temporal"] = context.model_dump(mode="json")
        normalized_messages.append(item)
    return normalized_messages


def normalize_messages(
    messages: Sequence[Mapping[str, Any]],
    *,
    occurred_at: DateInput = None,
    observed_at: DateInput = None,
    source_id: Any = None,
    message_id: Any = None,
    timezone: TimezoneInput = None,
) -> list[dict[str, Any]]:
    return normalize_temporal_messages(
        messages,
        occurred_at=occurred_at,
        observed_at=observed_at,
        source_id=source_id,
        message_id=message_id,
        timezone=timezone,
    )


def context_from_message(message: Mapping[str, Any]) -> TemporalMessageContext:
    temporal = message.get("temporal")
    if isinstance(temporal, Mapping):
        try:
            return TemporalMessageContext.model_validate(temporal)
        except ValueError:
            pass
    timezone_reference = message.get("occurred_at") or message.get("observed_at") or message.get("event_start")
    try:
        message_timezone = _coerce_timezone(message.get("timezone") or message.get("source_timezone"), timezone_reference)
    except ValueError:
        message_timezone = UTC
    occurred_at = _coerce_datetime(message.get("occurred_at"), message_timezone)
    observed_at = _coerce_datetime(message.get("observed_at"), message_timezone)
    event_start = _coerce_datetime(message.get("event_start"), message_timezone)
    event_end = _coerce_datetime(message.get("event_end"), message_timezone)
    source_span = message.get("source_span") if isinstance(message.get("source_span"), Mapping) else None
    return TemporalMessageContext(
        reference_at=occurred_at or observed_at or event_start,
        occurred_at=occurred_at,
        observed_at=observed_at,
        event_start=event_start,
        event_end=event_end,
        source_id=_string_id(message.get("source_id")),
        message_id=_string_id(message.get("message_id")),
        timezone=str(message_timezone),
        temporal_precision=str(message.get("temporal_precision") or ("exact" if (occurred_at or observed_at or event_start) else "unknown")),
        temporal_basis=str(message.get("temporal_basis") or ("message_occurred_at" if occurred_at else "message_observed_at" if observed_at else "unavailable")),
        source_start=message.get("source_start") if source_span is None else source_span.get("start"),
        source_end=message.get("source_end") if source_span is None else source_span.get("end"),
        source_span=dict(source_span) if source_span else None,
        original_text=message.get("original_text"),
        normalized_text=message.get("normalized_text"),
    )


def common_message_context(
    messages: Sequence[Mapping[str, Any]],
) -> TemporalMessageContext | None:
    contexts = [context_from_message(message) for message in messages]
    contexts = [context for context in contexts if context.reference_at is not None]
    if not contexts:
        return None
    references = {context.reference_at.isoformat() for context in contexts}
    if len(references) != 1:
        return TemporalMessageContext(
            timezone=contexts[0].timezone,
            temporal_basis="ambiguous_message_timestamps",
        )
    first = contexts[0]
    return TemporalMessageContext(
        reference_at=first.reference_at,
        occurred_at=first.occurred_at,
        observed_at=first.observed_at,
        event_start=first.event_start,
        event_end=first.event_end,
        source_id=first.source_id,
        message_id=first.message_id,
        timezone=first.timezone,
        temporal_precision=first.temporal_precision,
        temporal_basis=first.temporal_basis,
        source_start=first.source_start,
        source_end=first.source_end,
        source_span=first.source_span,
        matches=first.matches,
        original_text=first.original_text,
        normalized_text=first.normalized_text,
    )


__all__ = [
    "TemporalMatch",
    "TemporalMessageContext",
    "TemporalNormalizer",
    "TemporalText",
    "common_message_context",
    "context_from_message",
    "normalize_messages",
    "normalize_temporal_expression",
    "normalize_temporal_messages",
    "normalize_temporal_text",
    "resolve_temporal_expression",
]
