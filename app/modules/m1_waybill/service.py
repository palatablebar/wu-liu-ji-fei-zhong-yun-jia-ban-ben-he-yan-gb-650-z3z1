"""M1 编排：解码 → 拆表 → 单行归一 → 交给质量断言 → 落库（幂等）。"""

from __future__ import annotations

from decimal import Decimal

from app import config, manifest, store
from app.errors import DomainError
from app.modules.m1_waybill import decode, normalize, reader
from app.modules.m2_rates import service as rates
from app.modules.m3_quality import rules as quality
from app.reasons import sort_codes


def _sample_bytes(name: str) -> bytes:
    path = config.SAMPLE_DIR / name
    if not path.exists():
        raise DomainError("SAMPLE_MISSING", f"样例文件不存在：{name}", 404)
    return path.read_bytes()


def _draft(record: reader.Record, header: list[str], styles: set[str]) -> dict:
    codes: list[str] = []
    blocks: list[str] = []

    def take(values) -> None:
        for code in values:
            if code:
                codes.append(code)

    if record.truncated:
        blocks.append("TRUNCATED_TAIL")
    elif not record.arity_ok:
        blocks.append("ARITY_MISMATCH")

    waybill_no = (reader.cell(record, header, "waybill_no") or "").strip()
    carrier = (reader.cell(record, header, "carrier") or "").strip().upper()
    service = (reader.cell(record, header, "service") or "").strip().lower()
    zone_raw, zone_changed = normalize.fullwidth(reader.cell(record, header, "zone"))
    zone = zone_raw.strip().upper()
    if zone_changed:
        codes.append("FULLWIDTH_NORMALIZED")
    if not waybill_no or not carrier or not service or not zone:
        blocks.append("MISSING_KEY")

    weight_kg, weight_codes, weight_reason = normalize.to_kg(
        reader.cell(record, header, "weight"),
        reader.cell(record, header, "weight_unit"),
    )
    take(weight_codes)
    if weight_reason:
        blocks.append(weight_reason)

    dim_unit = reader.cell(record, header, "dim_unit")
    dims = []
    for axis in ("length", "width", "height"):
        value, axis_codes, axis_reason = normalize.to_cm(reader.cell(record, header, axis), dim_unit)
        take(axis_codes)
        if axis_reason:
            blocks.append(axis_reason)
        dims.append(value)

    if all(value is not None for value in dims):
        dim_reason = normalize.check_dims(*dims)
        if dim_reason:
            blocks.append(dim_reason)

    pickup, date_codes, date_reason, style = normalize.to_utc(
        reader.cell(record, header, "pickup_date")
    )
    take(date_codes)
    if date_reason:
        blocks.append(date_reason)
    if style:
        styles.add(style)

    declared, declared_codes = normalize.to_amount(reader.cell(record, header, "declared_value"))
    take(declared_codes)
    pieces = normalize.to_int(reader.cell(record, header, "pieces"))

    draft = {
        "line_no": record.line_no,
        "raw": record.raw,
        "waybill_no": waybill_no,
        "carrier": carrier,
        "service": service,
        "zone": zone,
        "pickup": pickup,
        "pickup_utc": pickup.isoformat().replace("+00:00", "Z") if pickup else "",
        "weight_kg": weight_kg,
        "length_cm": dims[0],
        "width_cm": dims[1],
        "height_cm": dims[2],
        "declared_value": declared,
        "pieces": pieces,
        "codes": codes,
        "blocks": blocks,
    }
    return draft


def import_bytes(raw: bytes, name: str) -> dict:
    digest = manifest.sha256_bytes(raw)
    run_id = manifest.make_run_id(digest)
    existing = store.get_run(run_id)
    if existing and int(existing.get("rows_in") or 0) > 0:
        return {
            "run_id": run_id,
            "reused": True,
            "rows_in": int(existing["rows_in"]),
            "rows_ok": int(existing["rows_ok"]),
            "rows_quarantined": int(existing["rows_quarantined"]),
            "input_sha256": digest,
            "input_name": existing.get("input_name", name),
            "notes": existing.get("notes", ""),
        }

    text, file_codes = decode.decode_bytes(raw)
    text = decode.normalize_newlines(text)
    sheet = reader.read_sheet(text, file_codes)

    keys = rates.key_index()
    known_carriers = rates.carriers()
    styles: set[str] = set()
    drafts = [_draft(record, sheet.header, styles) for record in sheet.records]

    quality.apply_tz_styles(drafts, styles)
    for draft in drafts:
        if not draft["blocks"]:
            draft["blocks"].extend(quality.check_reference(draft, keys, known_carriers))
    quality.dedupe(drafts)

    good: list[dict] = []
    bad: list[dict] = []
    for draft in drafts:
        if draft["blocks"]:
            for code in sort_codes(draft["blocks"]):
                bad.append({
                    "line_no": draft["line_no"],
                    "waybill_no": draft["waybill_no"],
                    "code": code,
                    "detail": " ".join(sort_codes(draft["codes"] + draft["blocks"])),
                    "raw": draft["raw"],
                })
            continue
        good.append({
            "line_no": draft["line_no"],
            "waybill_no": draft["waybill_no"],
            "carrier": draft["carrier"],
            "service": draft["service"],
            "zone": draft["zone"],
            "pickup_utc": draft["pickup_utc"],
            "weight_kg": str(draft["weight_kg"]),
            "length_cm": str(draft["length_cm"]),
            "width_cm": str(draft["width_cm"]),
            "height_cm": str(draft["height_cm"]),
            "declared_value": str(draft["declared_value"]),
            "pieces": draft["pieces"],
            "codes": ",".join(sort_codes(draft["codes"])),
        })

    quarantined_lines = len({item["line_no"] for item in bad})
    notes = manifest.dumps({
        "file_codes": sort_codes(sheet.codes),
        "segments": sheet.segments,
        "duplicate_headers": sheet.duplicate_headers,
        "empty_rows": sheet.empty_rows,
        "state": sheet.state,
        "tz_styles": sorted(styles),
    })

    store.replace_waybills(run_id, good)
    store.replace_quarantine(run_id, bad)
    now = manifest.utc_now_iso()
    store.upsert_run(run_id, {
        "input_name": name,
        "input_sha256": digest,
        "rules_version": config.RULES_VERSION,
        "profile": config.PROFILE,
        "rows_in": len(sheet.records),
        "rows_ok": len(good),
        "rows_quarantined": quarantined_lines,
        "rate_digest": rates.rate_digest(),
        "stages": "ingest",
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    })
    return {
        "run_id": run_id,
        "reused": False,
        "rows_in": len(sheet.records),
        "rows_ok": len(good),
        "rows_quarantined": quarantined_lines,
        "input_sha256": digest,
        "input_name": name,
        "notes": notes,
    }


def import_sample(name: str = config.SAMPLE_WAYBILLS) -> dict:
    return import_bytes(_sample_bytes(name), name)


def ensure_sample_run() -> dict:
    """启动后页面要能直接演示：库中没有运单时先把样例跑一遍采信。"""
    existing = store.latest_run_id()
    if existing:
        row = store.get_run(existing)
        if row and int(row.get("rows_in") or 0) > 0:
            return {"run_id": existing, "reused": True, "bootstrapped": False}
    result = import_sample()
    return {**result, "bootstrapped": True}


def rows_for(run_id: str) -> list[dict]:
    return store.waybills(run_id)


def counts(run_id: str) -> dict:
    run = store.get_run(run_id) or {}
    return {
        "rows_in": int(run.get("rows_in") or 0),
        "rows_ok": int(run.get("rows_ok") or 0),
        "rows_quarantined": int(run.get("rows_quarantined") or 0),
    }


def amount_total(run_id: str) -> Decimal:
    run = store.get_run(run_id) or {}
    raw = str(run.get("amount_total") or "0.00")
    try:
        return Decimal(raw)
    except Exception:  # noqa: BLE001 - 清单里的值异常时按 0 处理
        return Decimal("0.00")
