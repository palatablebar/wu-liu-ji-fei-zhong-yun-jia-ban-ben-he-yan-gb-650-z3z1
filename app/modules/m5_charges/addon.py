"""附加费：偏远固定额、燃油按百分比、保价按声明价值。

叠加顺序固定为 基础 → 续重 → 偏远 → 燃油 → 保价；燃油只对基础与续重计费。
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.m2_rates.surcharge import ADDON_ORDER
from app.modules.m5_charges.money import q2


def remote_amount(card: dict) -> Decimal:
    fee = q2(Decimal(card["remote_fee"]))
    return fee if fee > 0 else q2(Decimal("0"))


def fuel_amount(base_amount: Decimal, step_amount: Decimal, card: dict) -> Decimal:
    rate = Decimal(card["fuel_pct"])
    if rate <= 0:
        return q2(Decimal("0"))
    return q2((q2(base_amount) + q2(step_amount)) * rate)


def insurance_amount(declared_value: Decimal, card: dict) -> Decimal:
    rate = Decimal(card["insurance_pct"])
    if rate <= 0 or declared_value <= 0:
        return q2(Decimal("0"))
    return q2(Decimal(declared_value) * rate)


def order() -> tuple[str, ...]:
    return ADDON_ORDER
