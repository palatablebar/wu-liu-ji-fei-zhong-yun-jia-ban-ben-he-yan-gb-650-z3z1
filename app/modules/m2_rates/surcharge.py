"""附加费参数归一：百分比两种写法、附加费叠加顺序。"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

PERCENT_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*%$")

# 叠加顺序是规则的一部分：先基础与续重，再偏远，再按基础与续重算燃油，最后保价
ADDON_ORDER = ("base", "step", "remote", "fuel", "insurance")


def parse_percent(text: str) -> Decimal:
    """``8.5%``、``8.5``、``0.085`` 三种写法都归到小数。"""
    raw = (text or "").strip()
    if not raw:
        return Decimal("0")
    match = PERCENT_RE.match(raw)
    if match:
        return Decimal(match.group(1)) / Decimal("100")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return Decimal("0")
    if value > 1:
        return value / Decimal("100")
    return value


def parse_divisor(text: str, default: int = 6000) -> int:
    raw = (text or "").strip()
    if not raw:
        return default
    try:
        value = int(Decimal(raw))
    except (InvalidOperation, ValueError):
        return default
    return value if value > 0 else default


def addon_order() -> tuple[str, ...]:
    return ADDON_ORDER
