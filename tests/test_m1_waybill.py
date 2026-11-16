"""M1 运单采信：编码、拆表、列数、尾行、归一、幂等。"""

from __future__ import annotations

from fixtures import samples
from fixtures.expected import DUPLICATE_HEADERS, ROWS_IN, ROWS_OK, ROWS_QUARANTINED, SEGMENTS

from app.modules.m1_waybill import decode, normalize, reader
from app.modules.m1_waybill import service as waybills


def test_gb18030_fallback_decodes_chinese(sample_bytes):
    """TRAP-01：GB18030 混在 UTF-8 批次里必须能读出来。"""
    raw = sample_bytes("waybills_gb18030.csv")
    text, codes = decode.decode_bytes(raw)
    assert "ENCODING_FALLBACK" in codes
    assert "顺丰速运" in text
    assert "Ｚ１" in text

    ingest = waybills.import_bytes(raw, "waybills_gb18030.csv")
    assert ingest["rows_in"] == 4
    assert ingest["rows_ok"] == 4
    assert ingest["rows_quarantined"] == 0


def test_bom_stripped_on_first_column():
    """TRAP-02 同源：BOM 不能留在首列列名里。"""
    raw = b"\xef\xbb\xbf" + samples.csv_bytes([samples.row("WB-9001")])
    text, codes = decode.decode_bytes(raw)
    assert "BOM_STRIPPED" in codes
    sheet = reader.read_sheet(text)
    assert sheet.header[0] == "waybill_no"
    assert sheet.header[0] != "\ufeffwaybill_no"


def test_thousands_and_fullwidth_normalized():
    """TRAP-06：千分位与全角数字都要归一。"""
    value, suffix, codes = normalize.scan_number("2,500")
    assert value == 2500
    assert suffix == ""
    assert value == normalize.scan_number("２５００")[0]
    assert "FULLWIDTH_NORMALIZED" in normalize.scan_number("２５００")[2]

    kg, weight_codes, reason = normalize.to_kg("１２.５", "kg")
    assert reason == ""
    assert kg == normalize.to_kg("12.5", "kg")[0]
    assert "FULLWIDTH_NORMALIZED" in weight_codes


def test_unit_conversion_g_and_m():
    """TRAP-15：g→kg、m→cm 都要换算，不能直接当数字用。"""
    kg, codes, reason = normalize.to_kg("3200", "g")
    assert reason == ""
    assert str(kg) == "3.200"
    assert "UNIT_CONVERTED" in codes

    cm, dim_codes, dim_reason = normalize.to_cm("0.3", "m")
    assert dim_reason == ""
    assert str(cm) == "30.000"
    assert "UNIT_CONVERTED" in dim_codes

    assert normalize.to_kg("3200", "g")[0] * 1000 == 3200


def test_truncated_tail_row_flagged(sample_bytes):
    """TRAP-16：半行不能被当成有效运单。"""
    raw = sample_bytes("waybills_truncated.csv")
    text, codes = decode.decode_bytes(raw)
    sheet = reader.read_sheet(text)
    assert sheet.records[-1].truncated is True
    assert sheet.records[-1].arity_ok is False

    ingest = waybills.import_bytes(raw, "waybills_truncated.csv")
    assert ingest["rows_in"] == 3
    assert ingest["rows_ok"] == 1
    assert ingest["rows_quarantined"] == 2


def test_arity_mismatch_row_quarantined():
    """TRAP-05：列数不齐的行进隔离区并带原因码。"""
    raw = samples.csv_bytes([
        samples.row("WB-9101"),
        "WB-9102,SF,standard,Z1,2026-04-05T10:00:00+08:00,2,kg,20,20",
        samples.row("WB-9103"),
    ])
    ingest = waybills.import_bytes(raw, "arity.csv")
    assert ingest["rows_in"] == 3
    assert ingest["rows_ok"] == 2
    assert ingest["rows_quarantined"] == 1
    codes = [item["code"] for item in _quarantine(ingest["run_id"])]
    assert "ARITY_MISMATCH" in codes


def test_duplicate_header_counted_and_segments(sample_bytes):
    """TRAP-04 同源：分段导出留下的重复表头不能被当成一条记录。"""
    raw = sample_bytes("waybills_dirty.csv")
    text, _codes = decode.decode_bytes(raw)
    sheet = reader.read_sheet(text)
    assert sheet.duplicate_headers == DUPLICATE_HEADERS
    assert sheet.segments == SEGMENTS
    assert len(sheet.records) == ROWS_IN


def test_crlf_and_lf_mixed_keep_record_count():
    """TRAP-03 同源：CRLF 与 LF 混用不能把一条记录切成两条。"""
    raw = samples.csv_bytes(
        [samples.row("WB-9201"), samples.row("WB-9202")],
        newline="\n",
    ).replace(b"WB-9202", b"WB-9202")
    mixed = raw.replace(b"\n", b"\r\n")
    text, _codes = decode.decode_bytes(mixed)
    sheet = reader.read_sheet(decode.normalize_newlines(text))
    assert len(sheet.records) == 2
    assert [record.line_no for record in sheet.records] == [2, 3]


def test_sentinel_weight_is_not_zero():
    """TRAP-07 同源：哨兵不能被当成 0 参与计费。"""
    kg, _codes, reason = normalize.to_kg("-", "kg")
    assert kg is None
    assert reason == "SENTINEL_VALUE"
    assert normalize.to_kg("N/A", "kg")[2] == "SENTINEL_VALUE"
    assert normalize.to_kg("未知", "kg")[2] == "SENTINEL_VALUE"


def test_sample_counts_match_expected(pipeline):
    ingest = pipeline["ingest"]
    assert ingest["rows_in"] == ROWS_IN
    assert ingest["rows_ok"] == ROWS_OK
    assert ingest["rows_quarantined"] == ROWS_QUARANTINED


def test_reimport_same_file_returns_same_run(pipeline):
    first = pipeline["ingest"]
    again = waybills.import_sample()
    assert again["run_id"] == first["run_id"]
    assert again["reused"] is True
    assert again["rows_ok"] == first["rows_ok"]
    assert again["rows_in"] == first["rows_in"]


def _quarantine(run_id: str):
    from app import store

    return store.quarantine(run_id)
