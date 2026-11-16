"""M2 运价版本：半开区间择版、重叠检测、陈旧拒绝、百分比归一。"""

from __future__ import annotations

import pytest

from fixtures.expected import RATE_CARD_ROWS, RATE_KEYS, RATE_SET_VERSION

from app.errors import DomainError
from app.modules.m2_rates import ratecard, surcharge, version
from app.modules.m2_rates import service as rates


def _cards():
    return rates.cards()


def _bucket(carrier: str, service: str, zone: str):
    return ratecard.index_by_key(_cards()).get((carrier, service, zone), [])


def test_select_picks_april_version():
    bucket = _bucket("SF", "standard", "Z1")
    pickup, _codes, _reason, _style = _parse("2026-04-05T10:00:00+08:00")
    card, codes = version.select(bucket, pickup)
    assert codes == []
    assert card["version_id"] == "SF-standard-Z1-v2"
    assert card["first_price"] == "13.00"


def test_half_open_start_is_inclusive():
    """TRAP-23：恰好等于生效起点要命中该版。"""
    bucket = _bucket("SF", "standard", "Z1")
    pickup, _codes, _reason, _style = _parse("2026-04-01T00:00:00Z")
    card, codes = version.select(bucket, pickup)
    assert codes == []
    assert card["version_id"] == "SF-standard-Z1-v2"


def test_half_open_end_is_exclusive():
    """TRAP-23：恰好等于生效终点要落到下一版。"""
    bucket = _bucket("SF", "standard", "Z1")
    before, _a, _b, _c = _parse("2026-03-31T23:59:59Z")
    boundary, _d, _e, _f = _parse("2026-04-01T00:00:00Z")
    card_before, _ = version.select(bucket, before)
    card_boundary, _ = version.select(bucket, boundary)
    assert card_before["version_id"] == "SF-standard-Z1-v1"
    assert card_boundary["version_id"] == "SF-standard-Z1-v2"


def test_timezone_styles_land_in_same_version():
    """TRAP-11：Z 与 +08:00 表达同一时刻，必须落到同一版。"""
    bucket = _bucket("SF", "standard", "Z1")
    with_z = version.parse_utc("2026-04-02T02:00:00Z")
    with_offset = version.parse_utc("2026-04-02T10:00:00+08:00")
    assert with_z == with_offset
    assert version.select(bucket, with_z)[0]["version_id"] == version.select(bucket, with_offset)[0]["version_id"]


def test_overlap_detected_in_dirty_rate_file(sample_bytes):
    """TRAP-25：同分区两版相交必须被检测出来。"""
    cards, problems, _set_version = ratecard.parse_cards(
        ratecard.read_text(sample_bytes("rate_cards_overlap.csv"))[0]
    )
    assert problems == []
    overlaps = version.detect_overlaps(cards)
    assert len(overlaps) >= 1
    assert any(item["carrier"] == "SF" and item["zone"] == "Z1" for item in overlaps)
    assert all(item["code"] == "RATE_OVERLAP" for item in overlaps)


def test_overlap_rejects_import(sample_bytes):
    """TRAP-25：重叠的运价集整份拒绝装载。"""
    report = rates.audit(sample_bytes("rate_cards_overlap.csv"), "rate_cards_overlap.csv")
    assert report["ok"] is False
    assert len(report["overlaps"]) >= 1
    with pytest.raises(DomainError) as excinfo:
        rates.import_rate_set(sample_bytes("rate_cards_overlap.csv"), "rate_cards_overlap.csv")
    assert excinfo.value.code == "RATE_OVERLAP"
    assert excinfo.value.status == 409


def test_stale_rate_set_rejected(sample_bytes):
    """TRAP-26：旧版本运价集不能覆盖现有版本。"""
    text = ratecard.read_text(sample_bytes("rate_cards.csv"))[0]
    lines = [line for line in text.splitlines() if line.strip()]
    downgraded = "\n".join(
        [lines[0]] + [line.rsplit(",", 1)[0] + ",1" for line in lines[1:]]
    )
    report = rates.audit(downgraded.encode("utf-8"), "old.csv")
    assert report["stale"] is True
    with pytest.raises(DomainError) as excinfo:
        rates.import_rate_set(downgraded.encode("utf-8"), "old.csv")
    assert excinfo.value.code == "RATE_STALE"


def test_clean_rate_file_audits_ok(sample_bytes):
    report = rates.audit(sample_bytes("rate_cards.csv"), "rate_cards.csv")
    assert report["ok"] is True
    assert report["count"] == RATE_CARD_ROWS
    assert report["rate_set_version"] == RATE_SET_VERSION
    assert report["overlaps"] == []


def test_coverage_keys_match_rate_table():
    assert len(rates.key_index()) == RATE_KEYS
    assert ("SF", "standard", "Z4") in rates.key_index()
    assert ("SF", "economy", "Z4") not in rates.key_index()


def test_missing_key_gives_rate_missing():
    card, codes = version.select([], version.parse_utc("2026-04-05T00:00:00Z"))
    assert card is None
    assert codes == ["RATE_MISSING"]


def test_percent_forms_normalized():
    assert surcharge.parse_percent("8.5%") == surcharge.parse_percent("0.085")
    assert surcharge.parse_percent("8.5") == surcharge.parse_percent("0.085")
    assert str(surcharge.parse_percent("0.3%")) == "0.003"
    assert surcharge.parse_divisor("", 6000) == 6000
    assert surcharge.parse_divisor("0", 6000) == 6000


def _parse(text: str):
    from app.modules.m1_waybill import normalize

    return normalize.to_utc(text)
