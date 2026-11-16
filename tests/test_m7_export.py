"""M7 导出：账单 CSV、证据 CSV、运行清单、载体汇总。"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

from fixtures.expected import AMOUNT_TOTAL, ROWS_IN, ROWS_OK, ROWS_QUARANTINED, WAYBILLS

from app.modules.m3_quality import service as quality
from app.modules.m7_export import csv_out, invoice_out
from app.modules.m7_export import service as export


def _read(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_invoice_csv_rows_and_header(pipeline):
    rows = _read(export.invoice_csv(pipeline["run_id"]))
    assert len(rows) == len(WAYBILLS)
    assert list(rows[0]) == invoice_out.INVOICE_HEADER
    assert rows[0]["currency"] == "CNY"


def test_invoice_csv_totals_match(pipeline):
    rows = _read(export.invoice_csv(pipeline["run_id"]))
    total = sum(Decimal(row["total_amount"]) for row in rows)
    assert str(total) == AMOUNT_TOTAL
    for row in rows:
        assert row["total_amount"] == WAYBILLS[row["waybill_no"]]["total"]


def test_evidence_csv_has_line_numbers_and_codes(pipeline):
    rows = _read(export.evidence_csv(pipeline["run_id"]))
    assert len(rows) == len(WAYBILLS)
    assert list(rows[0]) == csv_out.HEADER
    assert all(int(row["line_no"]) > 0 for row in rows)
    flagged = [row for row in rows if row["reason_codes"]]
    assert any("VOLUMETRIC_APPLIED" in row["reason_codes"] for row in flagged)
    assert any("MIN_CHARGE_APPLIED" in row["reason_codes"] for row in flagged)


def test_manifest_has_run_id_and_input_digest(pipeline):
    doc = json.loads(export.manifest_json(pipeline["run_id"]))
    assert doc["run_id"] == pipeline["run_id"]
    assert len(doc["input_sha256"]) == 64
    assert doc["input_name"] == "waybills_dirty.csv"
    assert doc["rules_version"]
    assert doc["display_tz"] == "Asia/Shanghai"


def test_manifest_rows_and_amount_block(pipeline):
    doc = json.loads(export.manifest_json(pipeline["run_id"]))
    assert doc["rows"] == {
        "input": ROWS_IN,
        "billed": ROWS_OK,
        "quarantined": ROWS_QUARANTINED,
    }
    assert doc["amount"]["total"] == AMOUNT_TOTAL
    assert doc["amount"]["conserved"] is True
    assert doc["reconcile"]["balanced"] is True


def test_carrier_summary_covers_three_carriers(pipeline):
    summary = invoice_out.carrier_summary(pipeline["run_id"])
    carriers = [row["carrier"] for row in summary]
    assert carriers == ["JD", "SF", "YT"]
    total = sum(Decimal(row["total"].replace(",", "")) for row in summary)
    assert str(total) == AMOUNT_TOTAL


def test_quarantine_csv_export(pipeline):
    rows = _read(quality.csv_text(pipeline["run_id"]))
    assert rows
    assert {row["reason_code"] for row in rows} >= {"SENTINEL_VALUE", "DUP_CONFLICT"}
    assert all(int(row["line_no"]) > 0 for row in rows)


def test_export_is_deterministic(pipeline):
    first = export.invoice_csv(pipeline["run_id"])
    second = export.invoice_csv(pipeline["run_id"])
    assert first == second
    assert export.manifest_json(pipeline["run_id"]) == export.manifest_json(pipeline["run_id"])


def test_overview_matches_exports(pipeline):
    overview = export.overview(pipeline["run_id"])
    assert overview["invoice_rows"] == len(WAYBILLS)
    assert overview["evidence_rows"] == len(WAYBILLS)
    assert overview["amount_total"] == AMOUNT_TOTAL
    assert overview["rows"]["input"] == ROWS_IN
