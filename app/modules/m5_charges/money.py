"""金额量化与守恒：一律 Decimal，2 位小数，禁止 float 累加（TRAP-10）。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app import config

Q2 = config.MONEY_QUANT
ZERO = Decimal("0.00")


def q2(value: Decimal) -> Decimal:
    return value.quantize(Q2, rounding=ROUND_HALF_UP)


def total(values) -> Decimal:
    """分项求和：先把每项量化到分，再相加，合计必然等于分项之和。"""
    return q2(sum((q2(Decimal(str(v))) for v in values), ZERO))


def conserved(amount: Decimal, parts) -> bool:
    return q2(Decimal(str(amount))) == total(parts)


def delta(amount: Decimal, parts) -> Decimal:
    return q2(Decimal(str(amount))) - total(parts)
