"""M3 质量隔离：原因码分级、重复键冲突、分布、证据 CSV、质量分。"""

from __future__ import annotations

from fixtures import samples
from fixtures.expected import QUARANTINE_CODES, ROWS_IN, ROWS_OK, ROWS_QUARANTINED

from app import store
from app.modules.m1_waybill import service as waybills
from app.modules.m3_quality import quarantine, rules
from app.modules.m3_quality import service as quality


def test_sentinel_rows_quarantined(pipeline):
    """TRAP-07：哨兵行进隔离区，不参与合计。"""
    items = quality.rows(pipeline["run_id"])
    sentinel_waybills = {item["waybill_no"] for item in items if item["code"] == "SENTINEL_VALUE"}
    assert {"WB-1007", "WB-1008"} <= sentinel_waybills
    billed = {row["waybill_no"] for row in waybills.rows_for(pipeline["run_id"])}
    assert "WB-1007" not in billed
    assert "WB-1008" not in billed


def test_duplicate_conflict_keeps_first(pipeline):
    """TRAP-14：重复运单取值冲突时保留首条，首条重量是 3.200 kg。"""
    rows = {row["waybill_no"]: row for row in waybills.rows_for(pipeline["run_id"])}
    assert rows["WB-1001"]["weight_kg"] == "3.200"
    codes = [item["code"] for item in quality.rows(pipeline["run_id"])]
    assert codes.count("DUP_CONFLICT") == 1


def test_identical_duplicate_marked_separately():
    """取值一致的重复运单记 DUPLICATE_WAYBILL，与冲突区分开。"""
    raw = samples.csv_bytes([samples.row("WB-9301"), samples.row("WB-9301")])
    ingest = waybills.import_bytes(raw, "dup_same.csv")
    assert ingest["rows_ok"] == 1
    assert ingest["rows_quarantined"] == 1
    codes = [item["code"] for item in store.quarantine(ingest["run_id"])]
    assert "DUPLICATE_WAYBILL" in codes
    assert "DUP_CONFLICT" not in codes


def test_unknown_carrier_and_missing_zone(pipeline):
    items = {item["waybill_no"]: item["code"] for item in quality.rows(pipeline["run_id"])}
    assert items["WB-1010"] == "UNKNOWN_CARRIER"
    assert items["WB-1009"] == "RATE_MISSING"


def test_distribution_covers_all_codes(pipeline):
    distribution = quality.distribution(pipeline["run_id"])
    codes = [bucket["code"] for bucket in distribution]
    assert sorted(codes) == sorted(QUARANTINE_CODES)
    block_first = [bucket["level"] for bucket in distribution]
    assert block_first[0] == "block"
    total = sum(bucket["count"] for bucket in distribution)
    assert total >= ROWS_QUARANTINED


def test_quarantine_csv_header_and_rows(pipeline):
    body = quality.csv_text(pipeline["run_id"])
    lines = body.strip().split("\n")
    assert lines[0].split(",")[:3] == ["line_no", "waybill_no", "reason_code"]
    assert len(lines) == ROWS_QUARANTINED + 1 + (sum(
        1 for bucket in quality.distribution(pipeline["run_id"]) for _ in bucket["lines"]
    ) - ROWS_QUARANTINED)


def test_metrics_rows_and_pass_rate(pipeline):
    metrics = quality.metrics(pipeline["run_id"])
    assert metrics["rows_in"] == ROWS_IN
    assert metrics["rows_ok"] == ROWS_OK
    assert metrics["quarantined_lines"] == ROWS_QUARANTINED
    assert metrics["pass_rate"] == "55.6"


def test_quality_score_bounded(pipeline):
    metrics = quality.metrics(pipeline["run_id"])
    score = float(metrics["quality_score"])
    assert 0 <= score <= 100
    assert score < float(metrics["pass_rate"]) or score == float(metrics["pass_rate"])


def test_codes_sorted_block_before_info():
    draft = {"carrier": "SF", "service": "standard", "zone": "Z4"}
    assert rules.check_reference(draft, set(), {"SF"}) == ["RATE_MISSING"]
    unknown = {"carrier": "ZZ", "service": "standard", "zone": "Z1"}
    assert rules.check_reference(unknown, set(), {"SF"}) == ["UNKNOWN_CARRIER"]
    hit = {"carrier": "SF", "service": "standard", "zone": "Z1"}
    assert rules.check_reference(hit, {("SF", "standard", "Z1")}, {"SF"}) == []
    assert rules.check_reference({"carrier": "", "service": "", "zone": ""}, set(), set()) == []


def test_tz_mixed_marks_rows_but_keeps_utc():
    drafts = [
        {"pickup": object(), "codes": [], "blocks": [], "waybill_no": "A"},
        {"pickup": None, "codes": [], "blocks": [], "waybill_no": "B"},
    ]
    marked = rules.apply_tz_styles(drafts, {"z", "offset"})
    assert marked == 1
    assert "TZ_MIXED" in drafts[0]["codes"]
    assert drafts[1]["codes"] == []


def test_line_count_dedupes_multi_code_rows():
    items = [
        {"line_no": 4, "code": "ARITY_MISMATCH"},
        {"line_no": 4, "code": "TRUNCATED_TAIL"},
        {"line_no": 9, "code": "SENTINEL_VALUE"},
    ]
    assert quarantine.line_count(items) == 2
