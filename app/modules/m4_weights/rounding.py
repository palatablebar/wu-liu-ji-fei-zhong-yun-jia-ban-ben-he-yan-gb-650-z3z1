"""计费重进位：按版本台阶向上取整（0.5 kg 一档），并算续重段数。"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

ZERO = Decimal("0")


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    """向上取到台阶的整数倍；台阶非正时原值返回。"""
    if step is None or step <= ZERO:
        return value
    buckets = (value / step).to_integral_value(rounding=ROUND_CEILING)
    return buckets * step


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step is None or step <= ZERO:
        return value
    buckets = (value / step).to_integral_value(rounding=ROUND_FLOOR)
    return buckets * step


def steps_above(billable_kg: Decimal, first_weight_kg: Decimal, step: Decimal) -> int:
    """首重以内为 0 段；超出部分按台阶向上取段数。"""
    if step is None or step <= ZERO:
        return 0
    over = billable_kg - first_weight_kg
    if over <= ZERO:
        return 0
    return int((over / step).to_integral_value(rounding=ROUND_CEILING))
