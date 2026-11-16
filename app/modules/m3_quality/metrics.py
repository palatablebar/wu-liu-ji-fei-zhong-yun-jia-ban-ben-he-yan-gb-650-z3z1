"""质量指标：通过率与按原因级别扣分的质量分。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.reasons import level

ONE = Decimal("1")
Q1 = Decimal("0.1")


def q1(value: Decimal) -> Decimal:
    return value.quantize(Q1, rounding=ROUND_HALF_UP)


def pass_rate(rows_in: int, rows_ok: int) -> Decimal:
    if rows_in <= 0:
        return Decimal("0")
    return q1(Decimal(rows_ok) * Decimal("100") / Decimal(rows_in))


def weighted_penalty(distribution: list[dict]) -> Decimal:
    """阻断码整条计 1，标记码计 0.2；同一行多码不重复扣。"""
    penalty = Decimal("0")
    seen: set[int] = set()
    for bucket in distribution:
        weight = Decimal("1") if level(bucket["code"]) == "block" else Decimal("0.2")
        for line in bucket["lines"]:
            if line in seen:
                continue
            seen.add(line)
            penalty += weight
    return penalty


def quality_score(rows_in: int, distribution: list[dict]) -> Decimal:
    if rows_in <= 0:
        return Decimal("0")
    penalty = weighted_penalty(distribution)
    score = (ONE - penalty / Decimal(rows_in)) * Decimal("100")
    if score < 0:
        score = Decimal("0")
    return q1(score)


def summary(rows_in: int, rows_ok: int, items: list[dict], distribution: list[dict]) -> dict:
    lines = len({item["line_no"] for item in items})
    return {
        "rows_in": rows_in,
        "rows_ok": rows_ok,
        "quarantined_lines": lines,
        "pass_rate": str(pass_rate(rows_in, rows_ok)),
        "quality_score": str(quality_score(rows_in, distribution)),
        "codes": [bucket["code"] for bucket in distribution],
    }
