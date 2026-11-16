"""运价版本编排：装载、校验、择版入口。"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from app import config, manifest, store
from app.errors import DomainError
from app.modules.m2_rates import ratecard, version


def _read_sample(name: str) -> bytes:
    path = config.SAMPLE_DIR / name
    if not path.exists():
        raise DomainError("SAMPLE_MISSING", f"样例文件不存在：{name}", 404)
    return path.read_bytes()


def seed_sample(force: bool = False) -> dict:
    """启动时把随仓库的运价表装进库；已有运价且非强制时不动。"""
    if store.rate_cards() and not force:
        return {"applied": False, "count": len(store.rate_cards()),
                "rate_set_version": store.max_rate_set_version()}
    raw = _read_sample(config.SAMPLE_RATES)
    text, codes = ratecard.read_text(raw)
    cards, problems, set_version = ratecard.parse_cards(text)
    if problems:
        raise DomainError("RATE_PARSE_FAILED", ";".join(problems[:5]), 422)
    store.replace_rate_cards(cards, set_version, manifest.utc_now_iso())
    return {"applied": True, "count": len(cards), "rate_set_version": set_version,
            "codes": codes}


def audit(raw: bytes, name: str = "") -> dict:
    """只校验不落库：解析问题、版本重叠、陈旧版本。"""
    text, codes = ratecard.read_text(raw)
    cards, problems, set_version = ratecard.parse_cards(text)
    overlaps = version.detect_overlaps(cards)
    current = store.max_rate_set_version()
    stale = bool(current) and set_version < current
    keys = sorted({(c["carrier"], c["service"], c["zone"]) for c in cards})
    return {
        "file": name,
        "codes": codes,
        "count": len(cards),
        "rate_set_version": set_version,
        "current_rate_set_version": current,
        "problems": problems,
        "overlaps": overlaps,
        "stale": stale,
        "coverage": len(keys),
        "ok": not problems and not overlaps and not stale,
        "digest": hashlib.sha256(raw).hexdigest(),
    }


def import_rate_set(raw: bytes, name: str = "") -> dict:
    """校验通过才整体替换；陈旧版本拒绝覆盖（TRAP-26）。"""
    report = audit(raw, name)
    if report["stale"]:
        raise DomainError(
            "RATE_STALE",
            f"运价集版本 {report['rate_set_version']} 低于现有 {report['current_rate_set_version']}",
            409,
        )
    if report["problems"]:
        raise DomainError("RATE_PARSE_FAILED", ";".join(report["problems"][:5]), 422)
    if report["overlaps"]:
        first = report["overlaps"][0]
        raise DomainError(
            "RATE_OVERLAP",
            f"{first['carrier']}/{first['service']}/{first['zone']} "
            f"{first['left']} 与 {first['right']} 生效区间重叠",
            409,
        )
    text, _codes = ratecard.read_text(raw)
    cards, _problems, set_version = ratecard.parse_cards(text)
    store.replace_rate_cards(cards, set_version, manifest.utc_now_iso())
    return {"applied": True, "count": len(cards), "rate_set_version": set_version}


def cards() -> list[dict]:
    return store.rate_cards()


def index() -> dict:
    return ratecard.index_by_key(cards())


def key_index() -> set[tuple[str, str, str]]:
    return {(c["carrier"], c["service"], c["zone"]) for c in cards()}


def overlaps() -> list[dict]:
    return version.detect_overlaps(cards())


def select_card(index_map: dict, carrier: str, service: str, zone: str,
                pickup_utc) -> tuple[dict | None, list[str]]:
    bucket = index_map.get((carrier, service, zone), [])
    return version.select(bucket, pickup_utc)


def rate_digest() -> str:
    payload = manifest.dumps([
        [c["carrier"], c["service"], c["zone"], c["version_id"], c["effective_from"],
         c["effective_to"], c["first_price"], c["step_price"], c["min_charge"],
         c["volume_divisor"], c["fuel_pct"], c["remote_fee"], c["insurance_pct"]]
        for c in cards()
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def coverage() -> list[dict]:
    return version.window_summary(cards())


def money_of(card: dict, field: str) -> Decimal:
    return Decimal(card[field])


def sample_names() -> dict:
    return {"rates": config.SAMPLE_RATES, "overlap": config.SAMPLE_RATES_OVERLAP}


def carriers() -> set[str]:
    return {c["carrier"] for c in cards()}
