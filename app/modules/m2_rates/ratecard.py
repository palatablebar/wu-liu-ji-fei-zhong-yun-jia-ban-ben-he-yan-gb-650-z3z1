"""运价表解析：列契约、版本行、数值归一。

运价表与运单表是两份独立输入，本文件自带小解码，不依赖采信模块。
"""

from __future__ import annotations

import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation

from app.modules.m2_rates.surcharge import parse_divisor, parse_percent

CARD_COLUMNS = (
    "carrier", "service", "zone", "version_id", "effective_from", "effective_to",
    "first_weight_kg", "first_price", "step_weight_kg", "step_price", "min_charge",
    "volume_divisor", "fuel_pct", "remote_fee", "insurance_pct", "currency",
    "rate_set_version",
)

Q3 = Decimal("0.001")
Q2 = Decimal("0.01")


def dec(text: str, default: str = "0") -> Decimal:
    raw = unicodedata.normalize("NFKC", text or "").strip().replace(",", "")
    if not raw:
        return Decimal(default)
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal(default)


def money(value: Decimal) -> str:
    return str(value.quantize(Q2))


def weight(value: Decimal) -> str:
    return str(value.quantize(Q3))


def read_text(raw: bytes) -> tuple[str, list[str]]:
    codes: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        codes.append("BOM_STRIPPED")
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding == "gb18030":
            codes.append("ENCODING_FALLBACK")
        return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n"), codes
    return "", codes + ["ENCODING_FAILED"]


def parse_cards(text: str) -> tuple[list[dict], list[str], int]:
    """返回 (运价行, 解析问题, 运价集版本)。问题按 ``行号:代码`` 形式给出。"""
    reader = csv.reader(io.StringIO(text, newline=""))
    problems: list[str] = []
    header: list[str] | None = None
    cards: list[dict] = []
    rate_set_version = 0

    for cells in reader:
        if not cells or not any((c or "").strip() for c in cells):
            continue
        if header is None:
            header = [(c or "").strip().lower() for c in cells]
            missing = [c for c in CARD_COLUMNS if c not in header]
            if missing:
                problems.append("表头缺列:" + ",".join(missing))
                return [], problems, 0
            continue

        row = dict(zip(header, [c if i < len(cells) else "" for i, c in enumerate(cells)]))
        line_no = reader.line_num
        carrier = (row.get("carrier") or "").strip().upper()
        service = (row.get("service") or "").strip().lower()
        zone = unicodedata.normalize("NFKC", row.get("zone") or "").strip().upper()
        if not carrier or not service or not zone:
            problems.append(f"{line_no}:MISSING_KEY")
            continue
        effective_from = (row.get("effective_from") or "").strip()
        effective_to = (row.get("effective_to") or "").strip()
        if not effective_from or not effective_to:
            problems.append(f"{line_no}:MISSING_KEY")
            continue
        if effective_from >= effective_to:
            problems.append(f"{line_no}:RATE_OVERLAP")
            continue
        card = {
            "carrier": carrier,
            "service": service,
            "zone": zone,
            "version_id": (row.get("version_id") or f"{carrier}-{service}-{zone}").strip(),
            "effective_from": effective_from,
            "effective_to": effective_to,
            "first_weight_kg": weight(dec(row.get("first_weight_kg"), "1")),
            "first_price": money(dec(row.get("first_price"))),
            "step_weight_kg": weight(dec(row.get("step_weight_kg"), "0.5")),
            "step_price": money(dec(row.get("step_price"))),
            "min_charge": money(dec(row.get("min_charge"))),
            "volume_divisor": parse_divisor(row.get("volume_divisor")),
            "fuel_pct": str(parse_percent(row.get("fuel_pct"))),
            "remote_fee": money(dec(row.get("remote_fee"))),
            "insurance_pct": str(parse_percent(row.get("insurance_pct"))),
            "currency": (row.get("currency") or "CNY").strip().upper(),
            "rate_set_version": int(dec(row.get("rate_set_version"), "0")),
        }
        rate_set_version = max(rate_set_version, card["rate_set_version"])
        cards.append(card)

    if not cards and not problems:
        problems.append("0:EMPTY_FILE")
    return cards, problems, rate_set_version


def index_by_key(cards: list[dict]) -> dict[tuple[str, str, str], list[dict]]:
    index: dict[tuple[str, str, str], list[dict]] = {}
    for card in cards:
        key = (card["carrier"], card["service"], card["zone"])
        index.setdefault(key, []).append(card)
    for bucket in index.values():
        bucket.sort(key=lambda c: c["effective_from"])
    return index


def price_of(card: dict, field: str) -> Decimal:
    return Decimal(card[field])
