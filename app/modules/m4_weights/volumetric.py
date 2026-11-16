"""体积重：长×宽×高 ÷ 服务除数，量化到 0.001 kg。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app import config

Q3 = config.VOLUME_QUANT


def volume_cm3(length_cm: Decimal, width_cm: Decimal, height_cm: Decimal) -> Decimal:
    return length_cm * width_cm * height_cm


def volumetric_kg(length_cm: Decimal, width_cm: Decimal, height_cm: Decimal,
                  divisor: int) -> Decimal:
    """除数为 0 或负数时按 6000 处理，绝不抛 ZeroDivisionError。"""
    safe = divisor if divisor and divisor > 0 else 6000
    raw = volume_cm3(length_cm, width_cm, height_cm) / Decimal(safe)
    return raw.quantize(Q3, rounding=ROUND_HALF_UP)
