"""返利档位 CSV 解析与结构校验：区间连续不重叠、费率单调、月份合法。"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from app import config
from app.errors import DomainError

HEADER = ["carrier", "month", "tier_from", "tier_to", "rebate_pct"]
ZERO_PCT = Decimal("0.0000")


def parse_tiers(text: str) -> list[dict]:
    """把档位文本解析成结构化行；非法行收集为问题，不静默丢弃。"""
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in HEADER if c not in (reader.fieldnames or [])]
    if missing:
        raise DomainError(
            "REBATE_TIER_HEADER", f"返利档位缺列：{','.join(missing)}", 422
        )

    rows: list[dict] = []
    problems: list[str] = []
    for line_no, raw in enumerate(reader, start=2):
        carrier = (raw.get("carrier") or "").strip().upper()
        month = (raw.get("month") or "").strip()
        try:
            tier_from = Decimal((raw.get("tier_from") or "").strip())
            tier_to = Decimal((raw.get("tier_to") or "").strip())
            rebate_pct = Decimal((raw.get("rebate_pct") or "").strip())
        except (InvalidOperation, ValueError):
            problems.append(f"第{line_no}行：金额或费率无法解析")
            continue
        if not carrier or not month:
            problems.append(f"第{line_no}行：承运商或月份为空")
            continue
        if len(month) != 7 or month[4] != "-":
            problems.append(f"第{line_no}行：月份 {month} 不是 YYYY-MM")
            continue
        year, month_index = month.split("-")
        if not (year.isdigit() and month_index.isdigit()
                and 1 <= int(month_index) <= 12):
            problems.append(f"第{line_no}行：月份 {month} 越界")
            continue
        if tier_from < 0 or tier_to <= tier_from:
            problems.append(f"第{line_no}行：档位区间非法 [{tier_from}, {tier_to})")
            continue
        if rebate_pct < 0 or rebate_pct > 1:
            problems.append(f"第{line_no}行：费率 {rebate_pct} 不在 [0,1]")
            continue
        rows.append({
            "carrier": carrier,
            "month": month,
            "tier_from": str(tier_from),
            "tier_to": str(tier_to),
            "rebate_pct": str(rebate_pct),
        })

    structural = validate_continuity(rows)
    return rows, problems + structural


def validate_continuity(rows: list[dict]) -> list[str]:
    """同承运商同月份的档位必须从 0 起、半开首尾相接、费率单调不减。"""
    problems: list[str] = []
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["carrier"], row["month"]), []).append(row)

    for (carrier, month), tiers in sorted(groups.items()):
        ordered = sorted(tiers, key=lambda r: Decimal(r["tier_from"]))
        cursor = Decimal("0")
        previous_pct = ZERO_PCT
        for tier in ordered:
            low = Decimal(tier["tier_from"])
            high = Decimal(tier["tier_to"])
            pct = Decimal(tier["rebate_pct"])
            if low != cursor:
                problems.append(
                    f"{carrier} {month}：档位在 {cursor} 与 {low} 之间断档或重叠"
                )
                break
            if pct < previous_pct:
                problems.append(
                    f"{carrier} {month}：费率在 [{low}, {high}) 回退，违反单调不减"
                )
                break
            cursor = high
            previous_pct = pct
        else:
            if ordered and Decimal(ordered[-1]["tier_to"]) < config.REBATE_OPEN_TIER_TO:
                problems.append(f"{carrier} {month}：末档未开放到敞口上限")
    return problems


def group_by_carrier_month(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["carrier"], row["month"]), []).append(row)
    for tiers in groups.values():
        tiers.sort(key=lambda r: Decimal(r["tier_from"]))
    return groups
