"""分区价：首重价 + 续重单价 × 段数；低于最低收费时补差额。"""

from __future__ import annotations

from decimal import Decimal

from app.modules.m5_charges.money import q2


def first_amount(card: dict) -> Decimal:
    return q2(Decimal(card["first_price"]))


def step_amount(steps: int, card: dict) -> Decimal:
    if steps <= 0:
        return q2(Decimal("0"))
    return q2(Decimal(card["step_price"]) * Decimal(steps))


def min_topup(zone_amount: Decimal, card: dict) -> Decimal:
    floor = q2(Decimal(card["min_charge"]))
    gap = floor - q2(zone_amount)
    return q2(gap) if gap > 0 else q2(Decimal("0"))


def zone_amount(steps: int, card: dict) -> Decimal:
    return q2(first_amount(card) + step_amount(steps, card))
