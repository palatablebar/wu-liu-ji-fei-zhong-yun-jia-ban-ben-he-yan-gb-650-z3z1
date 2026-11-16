"""流式拆表：保留原始行号、识别重复表头、标记尾行截断。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field, replace

from app import config
from app.errors import DomainError

EMPTY_FILE = "empty_file"
HEADER_ONLY = "header_only"
BLANK_ROWS = "blank_rows"
READY = "ready"


@dataclass(frozen=True)
class Record:
    line_no: int
    cells: list[str]
    raw: str
    segment: int
    arity_ok: bool = True
    truncated: bool = False


@dataclass
class Sheet:
    header: list[str] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    segments: int = 1
    duplicate_headers: int = 0
    empty_rows: int = 0
    state: str = READY
    codes: list[str] = field(default_factory=list)


def normalize_header(cells: list[str]) -> list[str]:
    names: list[str] = []
    for cell in cells:
        name = (cell or "").strip().lstrip("\ufeff").strip().lower()
        name = config.HEADER_ALIASES.get(name, name)
        names.append(name)
    return names


def read_sheet(text: str, codes: list[str] | None = None) -> Sheet:
    sheet = Sheet(codes=list(codes or []))
    if not text.strip():
        sheet.state = EMPTY_FILE
        raise DomainError("EMPTY_FILE", "输入为空，没有可采信的记录", 422)

    lines = text.split("\n")
    reader = csv.reader(io.StringIO(text, newline=""))
    previous_line = 0
    header: list[str] | None = None
    segment = 1

    for cells in reader:
        start = previous_line + 1
        end = reader.line_num
        raw = "\n".join(lines[start - 1:end])[:400]
        previous_line = end

        if header is None:
            if not any((c or "").strip() for c in cells):
                sheet.empty_rows += 1
                continue
            header = normalize_header(cells)
            sheet.header = header
            continue

        if not any((c or "").strip() for c in cells):
            sheet.empty_rows += 1
            continue

        if normalize_header(cells) == header:
            sheet.duplicate_headers += 1
            sheet.codes.append("DUPLICATE_HEADER")
            segment += 1
            continue

        sheet.records.append(
            Record(
                line_no=end,
                cells=[(c or "") for c in cells],
                raw=raw,
                segment=segment,
                arity_ok=len(cells) == len(header),
            )
        )

    if header is None:
        sheet.state = EMPTY_FILE
        raise DomainError("EMPTY_FILE", "输入没有表头，无法确定列位置", 422)

    sheet.segments = segment
    if sheet.records:
        last = sheet.records[-1]
        if len(last.cells) < len(header):
            sheet.records[-1] = replace(last, arity_ok=False, truncated=True)
    elif sheet.empty_rows:
        sheet.state = BLANK_ROWS
    else:
        sheet.state = HEADER_ONLY
    return sheet


def column_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        return -1


def cell(record: Record, header: list[str], name: str) -> str:
    index = column_index(header, name)
    if index < 0 or index >= len(record.cells):
        return ""
    return record.cells[index]
