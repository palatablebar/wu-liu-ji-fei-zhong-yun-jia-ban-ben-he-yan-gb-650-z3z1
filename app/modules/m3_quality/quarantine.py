"""隔离区读写：原因分布、隔离行数、证据 CSV。"""

from __future__ import annotations

import csv
import io

from app.reasons import label, level, sort_codes


def line_count(items: list[dict]) -> int:
    return len({item["line_no"] for item in items})


def distribution(items: list[dict]) -> list[dict]:
    """按原因码统计；同一行可能命中多个码，行数按去重计。"""
    buckets: dict[str, dict] = {}
    for item in items:
        code = item["code"]
        bucket = buckets.setdefault(code, {
            "code": code,
            "label": label(code),
            "level": level(code),
            "count": 0,
            "lines": [],
        })
        bucket["count"] += 1
        if item["line_no"] not in bucket["lines"]:
            bucket["lines"].append(item["line_no"])
    ordered = sorted(buckets.values(), key=lambda b: (0 if b["level"] == "block" else 1, b["code"]))
    for bucket in ordered:
        bucket["lines"].sort()
        bucket["lines_text"] = ",".join(str(n) for n in bucket["lines"])
    return ordered


def codes_of(items: list[dict]) -> list[str]:
    return sort_codes([item["code"] for item in items])


def csv_text(items: list[dict]) -> str:
    """证据行：原始行号 + 原因码 + 中文标签 + 原值。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["line_no", "waybill_no", "reason_code", "reason_label", "detail", "raw"])
    for item in sorted(items, key=lambda i: (i["line_no"], i["code"])):
        writer.writerow([
            item["line_no"],
            item["waybill_no"],
            item["code"],
            label(item["code"]),
            item["detail"],
            (item["raw"] or "").replace("\n", "\\n"),
        ])
    return buffer.getvalue()
