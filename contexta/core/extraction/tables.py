from __future__ import annotations

import builtins
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass(frozen=True)
class _RawCell:
    value: str
    start: int
    end: int


_NULL_VALUES = {
    "",
    "-",
    "—",
    "–",
    "n/a",
    "n\\a",
    "na",
    "null",
    "none",
    "nil",
}
_INTEGER_RE = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)\.\d+|(?:\d+|\d{1,3}(?:,\d{3})+)(?:[eE][+-]?\d+))$"
)
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


def _unescape_cell(value: str) -> str:
    result = re.sub(r"\\([|\\`])", r"\1", value)
    return " ".join(result.split())


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _typed_value(raw_value: str) -> tuple[Any, str]:
    value = _strip_wrapping_quotes(_unescape_cell(raw_value))
    lowered = value.casefold()
    if lowered in _NULL_VALUES:
        return None, "null"
    if lowered in {"true", "yes", "y"}:
        return True, "boolean"
    if lowered in {"false", "no", "n"}:
        return False, "boolean"

    integer_candidate = value.replace(" ", "")
    if _INTEGER_RE.fullmatch(integer_candidate):
        return int(integer_candidate.replace(",", "")), "integer"

    float_candidate = value.replace(" ", "")
    if _FLOAT_RE.fullmatch(float_candidate):
        return float(float_candidate.replace(",", "")), "float"

    date_candidate = value
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", date_candidate):
        parts = date_candidate.split("/")
        date_candidate = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"

    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", date_candidate):
        try:
            parts = date_candidate.split("-")
            return date(int(parts[0]), int(parts[1]), int(parts[2])), "date"
        except ValueError:
            pass

    datetime_candidate = date_candidate[:-1] + "+00:00" if date_candidate.endswith("Z") else date_candidate
    try:
        parsed = datetime.fromisoformat(datetime_candidate)
    except ValueError:
        parsed = None
    if parsed is not None and (("T" in date_candidate) or (" " in date_candidate and any(char.isdigit() for char in date_candidate))):
        return parsed, "datetime"

    try:
        return date.fromisoformat(date_candidate), "date"
    except ValueError:
        pass
    return value, "string"


def _line_records(text: str) -> list[tuple[str, int, int]]:
    records: list[tuple[str, int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        records.append((content, offset, offset + len(content)))
        offset += len(line)
    if not records and text:
        records.append((text, 0, len(text)))
    return records


def _trim_cell(raw: str, segment_start: int) -> _RawCell:
    left_trimmed = raw.lstrip()
    right_trimmed = left_trimmed.rstrip()
    value_start = segment_start + len(raw) - len(left_trimmed)
    return _RawCell(
        value=right_trimmed,
        start=value_start,
        end=value_start + len(right_trimmed),
    )


def _split_markdown_row(line: str, line_start: int) -> list[_RawCell] | None:
    if "|" not in line or line.lstrip().startswith(">"):
        return None

    leading = len(line) - len(line.lstrip())
    start = leading
    if start < len(line) and line[start] == "|":
        start += 1
    trimmed_end = len(line.rstrip())
    end = trimmed_end
    if end > start and line[end - 1] == "|" and not _is_escaped(line, end - 1):
        end -= 1
    if start > end:
        return None

    cells: list[_RawCell] = []
    segment_start = start
    escaped = False
    code_delimiter: str | None = None
    index = start
    while index < end:
        character = line[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if character == "\\":
            escaped = True
            index += 1
            continue
        if character == "`":
            if code_delimiter is None:
                code_delimiter = "`"
            elif code_delimiter == "`":
                code_delimiter = None
            index += 1
            continue
        if character == "|" and code_delimiter is None:
            cells.append(_trim_cell(line[segment_start:index], segment_start))
            segment_start = index + 1
        index += 1
    cells.append(_trim_cell(line[segment_start:end], segment_start))
    return cells


def _is_escaped(value: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _is_separator_row(cells: list[_RawCell]) -> bool:
    return bool(cells) and all(
        _SEPARATOR_CELL_RE.fullmatch(re.sub(r"\s+", "", _unescape_cell(cell.value))) is not None
        for cell in cells
    )


def _column_type(cells: list[TableCell]) -> str:
    types = {cell.value_type for cell in cells if cell.value_type != "null"}
    if not types:
        return "null"
    if types == {"integer", "float"}:
        return "number"
    if len(types) == 1:
        return next(iter(types))
    if types.issubset({"date", "datetime"}):
        return "datetime"
    return "mixed"


def _alignment(cell: _RawCell) -> str | None:
    value = re.sub(r"\s+", "", cell.value)
    left = value.startswith(":")
    right = value.endswith(":")
    if left and right:
        return "center"
    if left:
        return "left"
    if right:
        return "right"
    return None


def _column_name(value: str, index: int, used: set[str]) -> tuple[str, str]:
    raw_name = _unescape_cell(value)
    base = raw_name or f"column_{index + 1}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return raw_name, candidate


class TableCell(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: Any = None
    normalized_value: Any = None
    raw_value: str = ""
    value_type: str = "string"
    row_index: int = 0
    column_index: int = 0
    column_name: str = ""
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None

    @model_validator(mode="after")
    def _synchronize_fields(self) -> TableCell:
        if self.normalized_value is None and self.value is not None:
            self.normalized_value = self.value
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @builtins.property
    def text(self) -> str:
        return self.raw_value

    @builtins.property
    def raw(self) -> str:
        return self.raw_value

    @builtins.property
    def original_value(self) -> str:
        return self.raw_value

    @builtins.property
    def normalized(self) -> Any:
        return self.normalized_value

    @builtins.property
    def original_text(self) -> str:
        return self.raw_value

    @builtins.property
    def normalized_text(self) -> Any:
        return self.normalized_value

    @builtins.property
    def type(self) -> str:
        return self.value_type

    @builtins.property
    def data_type(self) -> str:
        return self.value_type

    @builtins.property
    def column(self) -> str:
        return self.column_name

    @builtins.property
    def row(self) -> int:
        return self.row_index

    @builtins.property
    def span(self) -> dict[str, int] | None:
        return self.source_span


class TableColumn(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    raw_name: str | None = None
    index: int
    data_type: str = "string"
    alignment: str | None = None
    values: list[Any] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None

    @model_validator(mode="after")
    def _synchronize_fields(self) -> TableColumn:
        if not self.cells and self.values:
            self.cells = [
                TableCell(
                    value=value,
                    normalized_value=value,
                    raw_value=str(value) if value is not None else "",
                    value_type=self.data_type,
                    row_index=index,
                    column_index=self.index,
                    column_name=self.name,
                )
                for index, value in enumerate(self.values)
            ]
        if not self.values and self.cells:
            self.values = [cell.value for cell in self.cells]
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @builtins.property
    def type(self) -> str:
        return self.data_type

    @builtins.property
    def value_type(self) -> str:
        return self.data_type

    @builtins.property
    def column_name(self) -> str:
        return self.name

    @builtins.property
    def raw(self) -> str:
        return self.raw_name or self.name

    @builtins.property
    def span(self) -> dict[str, int] | None:
        return self.source_span


class TableRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int
    cells: list[TableCell] = Field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None

    @model_validator(mode="after")
    def _synchronize_fields(self) -> TableRow:
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @builtins.property
    def values(self) -> list[Any]:
        return [cell.value for cell in self.cells]

    @builtins.property
    def row_index(self) -> int:
        return self.index

    @builtins.property
    def record(self) -> dict[str, Any]:
        return {cell.column_name: cell.value for cell in self.cells}

    @builtins.property
    def data(self) -> dict[str, Any]:
        return self.record

    @builtins.property
    def as_dict(self) -> dict[str, Any]:
        return self.record

    @builtins.property
    def span(self) -> dict[str, int] | None:
        return self.source_span


class AtomicAssignmentCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    table_index: int = 0
    table_id: str | None = None
    row_index: int = 0
    column_index: int = 0
    key: str = ""
    property: str = ""
    column_name: str = ""
    subject: Any = None
    value: Any = None
    normalized_value: Any = None
    original_value: str = ""
    value_type: str = "string"
    source_id: str | None = None
    message_id: str | None = None
    source_message_id: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None
    subject_column_index: int = 0
    is_empty: bool = False
    is_subject: bool = False

    @model_validator(mode="after")
    def _synchronize_fields(self) -> AtomicAssignmentCandidate:
        if not self.property:
            self.property = self.key or self.column_name
        if not self.key:
            self.key = self.property or self.column_name
        if not self.column_name:
            self.column_name = self.key or self.property
        if self.source_message_id is None and self.message_id is not None:
            self.source_message_id = self.message_id
        if self.message_id is None and self.source_message_id is not None:
            self.message_id = self.source_message_id
        if self.normalized_value is None and self.value is not None:
            self.normalized_value = self.value
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @builtins.property
    def field(self) -> str:
        return self.property

    @builtins.property
    def predicate(self) -> str:
        return self.property

    @builtins.property
    def object_value(self) -> Any:
        return self.value

    @builtins.property
    def normalized(self) -> Any:
        return self.normalized_value

    @builtins.property
    def original_text(self) -> str:
        return self.original_value

    @builtins.property
    def normalized_text(self) -> Any:
        return self.normalized_value

    @builtins.property
    def type(self) -> str:
        return self.value_type

    @builtins.property
    def is_null(self) -> bool:
        return self.is_empty or self.value is None

    @builtins.property
    def column(self) -> str:
        return self.column_name

    @builtins.property
    def span(self) -> dict[str, int] | None:
        return self.source_span


class MarkdownTable(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int = 0
    table_id: str | None = None
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)
    assignment_candidates: list[AtomicAssignmentCandidate] = Field(default_factory=list)
    original_text: str = ""
    normalized_text: str = ""
    source_id: str | None = None
    message_id: str | None = None
    source_message_id: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, int] | None = None

    @model_validator(mode="after")
    def _synchronize_fields(self) -> MarkdownTable:
        if self.table_id is None:
            self.table_id = f"table_{self.index}"
        if self.source_message_id is None and self.message_id is not None:
            self.source_message_id = self.message_id
        if self.message_id is None and self.source_message_id is not None:
            self.message_id = self.source_message_id
        if not self.normalized_text and self.original_text:
            self.normalized_text = self.original_text.replace("\r\n", "\n").replace("\r", "\n")
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        return self

    @builtins.property
    def table_index(self) -> int:
        return self.index

    @builtins.property
    def headers(self) -> list[str]:
        return [column.name for column in self.columns]

    @builtins.property
    def cells(self) -> list[list[TableCell]]:
        return [row.cells for row in self.rows]

    @builtins.property
    def records(self) -> list[dict[str, Any]]:
        return [row.record for row in self.rows]

    @builtins.property
    def to_rows(self) -> list[dict[str, Any]]:
        return self.records

    @builtins.property
    def candidates(self) -> list[AtomicAssignmentCandidate]:
        return self.assignment_candidates

    @builtins.property
    def property_candidates(self) -> list[AtomicAssignmentCandidate]:
        return [candidate for candidate in self.assignment_candidates if not candidate.is_subject]

    @builtins.property
    def text(self) -> str:
        return self.original_text

    @builtins.property
    def raw_text(self) -> str:
        return self.original_text

    @builtins.property
    def normalized(self) -> str:
        return self.normalized_text

    @builtins.property
    def row_count(self) -> int:
        return len(self.rows)

    @builtins.property
    def column_count(self) -> int:
        return len(self.columns)

    @builtins.property
    def span(self) -> dict[str, int] | None:
        return self.source_span


def _span(start: int | None, end: int | None) -> dict[str, int] | None:
    if start is None or end is None:
        return None
    return {"start": start, "end": end}


def _make_cell(
    raw_cell: _RawCell,
    *,
    row_index: int,
    column_index: int,
    column_name: str,
) -> TableCell:
    value, value_type = _typed_value(raw_cell.value)
    return TableCell(
        value=value,
        normalized_value=value,
        raw_value=raw_cell.value,
        value_type=value_type,
        row_index=row_index,
        column_index=column_index,
        column_name=column_name,
        source_start=raw_cell.start,
        source_end=raw_cell.end,
        source_span=_span(raw_cell.start, raw_cell.end),
    )


def _make_empty_cell(
    *,
    row_index: int,
    column_index: int,
    column_name: str,
) -> TableCell:
    return TableCell(
        value=None,
        normalized_value=None,
        raw_value="",
        value_type="null",
        row_index=row_index,
        column_index=column_index,
        column_name=column_name,
    )


def _build_candidate(
    table: MarkdownTable,
    row: TableRow,
    cell: TableCell,
    *,
    subject: Any,
) -> AtomicAssignmentCandidate:
    return AtomicAssignmentCandidate(
        table_index=table.index,
        table_id=table.table_id,
        row_index=row.index,
        column_index=cell.column_index,
        key=cell.column_name,
        property=cell.column_name,
        column_name=cell.column_name,
        subject=subject,
        value=cell.value,
        normalized_value=cell.normalized_value,
        original_value=cell.raw_value,
        value_type=cell.value_type,
        source_id=table.source_id,
        message_id=table.message_id,
        source_message_id=table.source_message_id,
        source_start=cell.source_start,
        source_end=cell.source_end,
        source_span=cell.source_span,
        subject_column_index=0,
        is_empty=cell.value is None,
        is_subject=cell.column_index == 0,
    )


def _build_table(
    header: list[_RawCell],
    separator: list[_RawCell],
    data_lines: list[tuple[list[_RawCell], int, int]],
    *,
    text: str,
    table_index: int,
    table_start: int,
    table_end: int,
    source_id: str | None,
    message_id: str | None,
    offset: int,
    include_empty_candidates: bool,
    include_key_cells: bool,
) -> MarkdownTable:
    maximum_cells = max([len(header), len(separator), *(len(cells) for cells, _, _ in data_lines), 0])
    used_names: set[str] = set()
    column_names: list[str] = []
    raw_names: list[str] = []
    for column_index in range(maximum_cells):
        raw_value = header[column_index].value if column_index < len(header) else ""
        raw_name, name = _column_name(raw_value, column_index, used_names)
        raw_names.append(raw_name)
        column_names.append(name)

    rows: list[TableRow] = []
    for row_index, (raw_cells, line_start, line_end) in enumerate(data_lines):
        cells: list[TableCell] = []
        for column_index, column_name in enumerate(column_names):
            if column_index < len(raw_cells):
                raw_cell = raw_cells[column_index]
                shifted = _RawCell(
                    value=raw_cell.value,
                    start=raw_cell.start + offset,
                    end=raw_cell.end + offset,
                )
                cells.append(
                    _make_cell(
                        shifted,
                        row_index=row_index,
                        column_index=column_index,
                        column_name=column_name,
                    )
                )
            else:
                cells.append(
                    _make_empty_cell(
                        row_index=row_index,
                        column_index=column_index,
                        column_name=column_name,
                    )
                )
        rows.append(
            TableRow(
                index=row_index,
                cells=cells,
                source_start=line_start + offset,
                source_end=line_end + offset,
                source_span=_span(line_start + offset, line_end + offset),
            )
        )

    table = MarkdownTable(
        index=table_index,
        table_id=f"table_{table_index}",
        columns=[],
        rows=rows,
        assignment_candidates=[],
        original_text=text[table_start:table_end],
        normalized_text=text[table_start:table_end].replace("\r\n", "\n").replace("\r", "\n"),
        source_id=source_id,
        message_id=message_id,
        source_message_id=message_id,
        source_start=table_start + offset,
        source_end=table_end + offset,
        source_span=_span(table_start + offset, table_end + offset),
    )

    columns: list[TableColumn] = []
    for column_index, column_name in enumerate(column_names):
        column_cells = [row.cells[column_index] for row in rows]
        header_cell = header[column_index] if column_index < len(header) else None
        starts = [cell.source_start for cell in column_cells if cell.source_start is not None]
        ends = [cell.source_end for cell in column_cells if cell.source_end is not None]
        if header_cell is not None:
            starts.append(header_cell.start + offset)
            ends.append(header_cell.end + offset)
        column_start = min(starts) if starts else None
        column_end = max(ends) if ends else None
        columns.append(
            TableColumn(
                name=column_name,
                raw_name=raw_names[column_index],
                index=column_index,
                data_type=_column_type(column_cells),
                alignment=_alignment(separator[column_index]) if column_index < len(separator) else None,
                values=[cell.value for cell in column_cells],
                cells=column_cells,
                source_start=column_start,
                source_end=column_end,
                source_span=_span(column_start, column_end),
            )
        )
    table.columns = columns

    candidates: list[AtomicAssignmentCandidate] = []
    for row in rows:
        subject = row.cells[0].value if row.cells else None
        for cell in row.cells:
            if not include_key_cells and cell.column_index == 0:
                continue
            if not include_empty_candidates and cell.value is None:
                continue
            candidates.append(_build_candidate(table, row, cell, subject=subject))
    table.assignment_candidates = candidates
    return table


def parse_markdown_tables(
    text: str,
    *,
    source_id: str | None = None,
    message_id: str | None = None,
    offset: int = 0,
    include_empty_candidates: bool = True,
    include_key_cells: bool = True,
) -> list[MarkdownTable]:
    source = str(text or "")
    records = _line_records(source)
    tables: list[MarkdownTable] = []
    record_index = 0
    while record_index + 1 < len(records):
        header_line, header_start, _header_end = records[record_index]
        header = _split_markdown_row(header_line, header_start)
        separator_line, separator_start, separator_end = records[record_index + 1]
        separator = _split_markdown_row(separator_line, separator_start)
        if (
            header is None
            or separator is None
            or not _is_separator_row(separator)
            or len(header) != len(separator)
        ):
            record_index += 1
            continue

        data_lines: list[tuple[list[_RawCell], int, int]] = []
        next_index = record_index + 2
        while next_index < len(records):
            line, line_start, line_end = records[next_index]
            cells = _split_markdown_row(line, line_start)
            if cells is None or _is_separator_row(cells):
                break
            if next_index + 1 < len(records):
                next_line, next_start, _next_end = records[next_index + 1]
                next_cells = _split_markdown_row(next_line, next_start)
                if (
                    next_cells is not None
                    and _is_separator_row(next_cells)
                    and len(cells) == len(next_cells)
                ):
                    break
            data_lines.append((cells, line_start, line_end))
            next_index += 1

        table_end = data_lines[-1][2] if data_lines else separator_end
        tables.append(
            _build_table(
                header,
                separator,
                data_lines,
                text=source,
                table_index=len(tables),
                table_start=header_start,
                table_end=table_end,
                source_id=source_id,
                message_id=message_id,
                offset=offset,
                include_empty_candidates=include_empty_candidates,
                include_key_cells=include_key_cells,
            )
        )
        record_index = next_index if next_index > record_index + 1 else record_index + 2
    return tables


def parse_markdown_table(
    text: str,
    *,
    source_id: str | None = None,
    message_id: str | None = None,
    offset: int = 0,
    include_empty_candidates: bool = True,
    include_key_cells: bool = True,
) -> MarkdownTable | None:
    tables = parse_markdown_tables(
        text,
        source_id=source_id,
        message_id=message_id,
        offset=offset,
        include_empty_candidates=include_empty_candidates,
        include_key_cells=include_key_cells,
    )
    return tables[0] if tables else None


def extract_markdown_tables(text: str, **kwargs: Any) -> list[MarkdownTable]:
    return parse_markdown_tables(text, **kwargs)


def extract_tables(text: str, **kwargs: Any) -> list[MarkdownTable]:
    return parse_markdown_tables(text, **kwargs)


def parse_table(text: str, **kwargs: Any) -> MarkdownTable | None:
    return parse_markdown_table(text, **kwargs)


def assignment_candidates(
    table: MarkdownTable,
    *,
    include_subject: bool = True,
    include_empty: bool = True,
) -> list[AtomicAssignmentCandidate]:
    return [
        candidate
        for candidate in table.assignment_candidates
        if (include_subject or not candidate.is_subject) and (include_empty or not candidate.is_empty)
    ]


__all__ = [
    "AtomicAssignmentCandidate",
    "MarkdownTable",
    "TableCell",
    "TableColumn",
    "TableRow",
    "assignment_candidates",
    "extract_markdown_tables",
    "extract_tables",
    "parse_markdown_table",
    "parse_markdown_tables",
    "parse_table",
]
