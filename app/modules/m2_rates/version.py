"""生效区间择版：半开区间 [effective_from, effective_to)（TRAP-23 / TRAP-25）。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.reasons import sort_codes


def parse_utc(text: str) -> datetime | None:
    raw = (text or "").strip()
    if not raw:
        return None
    body = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        stamp = datetime.fromisoformat(body)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def active_at(cards: list[dict], pickup_utc: datetime) -> list[dict]:
    """半开区间：恰好等于生效起点的命中，恰好等于生效终点的落到下一版。"""
    hits = []
    for card in cards:
        start = parse_utc(card["effective_from"])
        end = parse_utc(card["effective_to"])
        if start is None or end is None:
            continue
        if start <= pickup_utc < end:
            hits.append(card)
    return hits


def select(cards: list[dict], pickup_utc: datetime) -> tuple[dict | None, list[str]]:
    """返回 (命中的版本, 原因码)。重叠时拒绝计费，不留半条。"""
    if not cards:
        return None, ["RATE_MISSING"]
    hits = active_at(cards, pickup_utc)
    if not hits:
        return None, ["RATE_MISSING"]
    if len(hits) > 1:
        return None, ["RATE_OVERLAP"]
    return hits[0], []


def detect_overlaps(cards: list[dict]) -> list[dict]:
    """同一 (承运商, 服务, 分区) 内任意两版生效区间相交即报出。"""
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for card in cards:
        grouped.setdefault((card["carrier"], card["service"], card["zone"]), []).append(card)

    found: list[dict] = []
    for key, bucket in sorted(grouped.items()):
        ordered = sorted(bucket, key=lambda c: (c["effective_from"], c["effective_to"]))
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                left, right = ordered[i], ordered[j]
                left_end = parse_utc(left["effective_to"])
                right_start = parse_utc(right["effective_from"])
                if left_end is None or right_start is None:
                    continue
                if right_start < left_end:
                    found.append({
                        "carrier": key[0],
                        "service": key[1],
                        "zone": key[2],
                        "left": left["version_id"],
                        "right": right["version_id"],
                        "from": right["effective_from"],
                        "to": left["effective_to"],
                        "code": "RATE_OVERLAP",
                    })
    return found


def window_summary(cards: list[dict]) -> list[dict]:
    """按 (承运商, 服务, 分区) 汇总版本窗口，供运价手册页展示。"""
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for card in cards:
        grouped.setdefault((card["carrier"], card["service"], card["zone"]), []).append(card)
    summary = []
    for key, bucket in sorted(grouped.items()):
        ordered = sorted(bucket, key=lambda c: c["effective_from"])
        summary.append({
            "carrier": key[0],
            "service": key[1],
            "zone": key[2],
            "versions": ordered,
            "count": len(ordered),
            "codes": sort_codes([c for c in ("RATE_OVERLAP" if len(detect_overlaps(bucket)) else "",) if c]),
        })
    return summary
