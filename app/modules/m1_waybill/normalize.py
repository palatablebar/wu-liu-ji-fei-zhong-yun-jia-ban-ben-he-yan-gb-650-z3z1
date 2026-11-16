"""列值归一：全角、千分位、单位后缀、时区（TRAP-06 / TRAP-11 / TRAP-15）。"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from app import config

NUMBER_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))(.*)$")
OFFSET_RE = re.compile(r"([+-]\d{2}:?\d{2})$")
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")

STYLE_Z = "z"
STYLE_OFFSET = "offset"
STYLE_NAIVE = "naive"


def fullwidth(text: str) -> tuple[str, bool]:
    """NFKC 归一：全角数字、全角字母、全角小数点一并处理。"""
    converted = unicodedata.normalize("NFKC", text or "")
    return converted, converted != (text or "")


def is_sentinel(text: str) -> bool:
    return (text or "").strip().lower() in config.SENTINELS


def quantize(value: Decimal, step: Decimal) -> Decimal:
    from decimal import ROUND_HALF_UP

    return value.quantize(step, rounding=ROUND_HALF_UP)


def scan_number(text: str) -> tuple[Decimal | None, str, list[str]]:
    """返回 (数值, 单位后缀, 诊断码)。千分位与单位后缀都在这里剥掉。"""
    codes: list[str] = []
    cleaned, changed = fullwidth(text)
    if changed:
        codes.append("FULLWIDTH_NORMALIZED")
    cleaned = cleaned.strip().replace(",", "").replace("，", "").replace(" ", "").replace("_", "")
    match = NUMBER_RE.match(cleaned)
    if not match:
        return None, "", codes + ["NUM_UNPARSEABLE"]
    body, suffix = match.group(1), match.group(2).strip().lower()
    try:
        return Decimal(body), suffix, codes
    except InvalidOperation:
        return None, "", codes + ["NUM_UNPARSEABLE"]


def _unit(column_text: str, suffix: str) -> str:
    unit = (column_text or "").strip().lower()
    return unit or suffix


def to_kg(value_text: str, unit_text: str) -> tuple[Decimal | None, list[str], str]:
    """重量归一到 kg；返回 (kg, 诊断码, 阻断原因)。"""
    if is_sentinel(value_text):
        return None, ["SENTINEL_VALUE"], "SENTINEL_VALUE"
    number, suffix, codes = scan_number(value_text)
    if number is None:
        return None, codes, "NUM_UNPARSEABLE"
    unit = _unit(unit_text, suffix)
    if is_sentinel(unit) and not suffix:
        return None, codes + ["UNIT_UNKNOWN"], "UNIT_UNKNOWN"
    factor = config.WEIGHT_UNITS.get(unit)
    if factor is None:
        return None, codes + ["UNIT_UNKNOWN"], "UNIT_UNKNOWN"
    if factor != Decimal("1"):
        codes.append("UNIT_CONVERTED")
    if number < 0:
        return None, codes + ["NUM_UNPARSEABLE"], "NUM_UNPARSEABLE"
    return quantize(number * factor, config.WEIGHT_QUANT), codes, ""


def to_cm(value_text: str, unit_text: str) -> tuple[Decimal | None, list[str], str]:
    """尺寸归一到 cm；0 或负数留给 check_dims 判定。"""
    if is_sentinel(value_text):
        return None, ["SENTINEL_VALUE"], "SENTINEL_VALUE"
    number, suffix, codes = scan_number(value_text)
    if number is None:
        return None, codes, "NUM_UNPARSEABLE"
    unit = _unit(unit_text, suffix)
    factor = config.DIM_UNITS.get(unit)
    if factor is None:
        return None, codes + ["UNIT_UNKNOWN"], "UNIT_UNKNOWN"
    if factor != Decimal("1"):
        codes.append("UNIT_CONVERTED")
    return quantize(number * factor, config.VOLUME_QUANT), codes, ""


def check_dims(length: Decimal, width: Decimal, height: Decimal) -> str:
    """三边都 >0 才可计费；任一边越界即结构异常。"""
    sides = (length, width, height)
    if any(side <= config.DIM_MIN_CM for side in sides):
        return "ZERO_DIMENSION"
    if any(side > config.DIM_MAX_CM for side in sides):
        return "DIM_RANGE"
    return ""


def to_utc(text: str) -> tuple[datetime | None, list[str], str, str]:
    """日期归一到 UTC；返回 (时刻, 诊断码, 阻断原因, 写法)。"""
    codes: list[str] = []
    raw = (text or "").strip()
    if not raw:
        return None, codes, "MISSING_KEY", ""
    cleaned, changed = fullwidth(raw)
    if changed:
        codes.append("FULLWIDTH_NORMALIZED")

    style = STYLE_NAIVE
    tzinfo: timezone | None = None
    body = cleaned
    if cleaned[-1] in ("Z", "z"):
        style = STYLE_Z
        tzinfo = timezone.utc
        body = cleaned[:-1]
    else:
        match = OFFSET_RE.search(cleaned)
        if match:
            style = STYLE_OFFSET
            token = match.group(1).replace(":", "")
            body = cleaned[: match.start()]
            sign = 1 if token[0] == "+" else -1
            tzinfo = timezone(sign * timedelta(hours=int(token[1:3]), minutes=int(token[3:5])))

    body = body.replace("T", " ").strip()
    stamp = None
    for fmt in DATE_FORMATS:
        try:
            stamp = datetime.strptime(body, fmt)
            break
        except ValueError:
            continue
    if stamp is None:
        return None, codes, "DATE_UNPARSEABLE", style
    if tzinfo is None:
        tzinfo = config.CN_TZ
    return stamp.replace(tzinfo=tzinfo).astimezone(timezone.utc), codes, "", style


def to_amount(text: str, default: str = "0.00") -> tuple[Decimal, list[str]]:
    """金额列：缺失与哨兵都按 0 处理（未保价），只在解析失败时给码。"""
    if is_sentinel(text):
        return Decimal(default), []
    number, _suffix, codes = scan_number(text)
    if number is None:
        return Decimal(default), codes + ["NUM_UNPARSEABLE"]
    return quantize(number, config.MONEY_QUANT), codes


def to_int(text: str, default: int = 1) -> int:
    number, _suffix, _codes = scan_number(text)
    if number is None:
        return default
    value = int(number)
    return value if value > 0 else default
