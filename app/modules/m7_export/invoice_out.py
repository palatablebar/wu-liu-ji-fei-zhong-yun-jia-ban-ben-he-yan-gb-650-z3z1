"""账单导出与运行清单：账单明细、按承运商汇总、可复算的清单 JSON。"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

from app import config, manifest, store
from app.modules.m6_reconcile import service as reconcile_service
from app.modules.m7_export import csv_out

INVOICE_HEADER = [
    "waybill_no", "carrier", "service", "zone", "pickup_utc", "billable_kg",
    "version_id", "base_amount", "step_amount", "remote_amount", "fuel_amount",
    "insurance_amount", "total_amount", "currency",
]


def currency_of() -> str:
    for card in store.rate_cards():
        return card["currency"]
    return "CNY"


def invoice_rows(run_id: str) -> list[dict]:
    currency = currency_of()
    rows = []
    for row in csv_out.rows(run_id):
        if not row["total_amount"]:
            continue
        rows.append({
            "waybill_no": row["waybill_no"],
            "carrier": row["carrier"],
            "service": row["service"],
            "zone": row["zone"],
            "pickup_utc": row["pickup_utc"],
            "billable_kg": row["billable_kg"],
            "version_id": row["version_id"],
            "base_amount": row["base_amount"],
            "step_amount": row["step_amount"],
            "remote_amount": row["remote_amount"],
            "fuel_amount": row["fuel_amount"],
            "insurance_amount": row["insurance_amount"],
            "total_amount": row["total_amount"],
            "currency": currency,
        })
    return rows


def invoice_csv(run_id: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(INVOICE_HEADER)
    for row in invoice_rows(run_id):
        writer.writerow([row[key] for key in INVOICE_HEADER])
    return buffer.getvalue()


def carrier_summary(run_id: str) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in invoice_rows(run_id):
        bucket = buckets.setdefault(row["carrier"], {
            "carrier": row["carrier"],
            "count": 0,
            "total": Decimal("0.00"),
            "currency": row["currency"],
        })
        bucket["count"] += 1
        bucket["total"] += Decimal(row["total_amount"])
    summary = []
    for bucket in sorted(buckets.values(), key=lambda b: b["carrier"]):
        summary.append({
            "carrier": bucket["carrier"],
            "count": bucket["count"],
            "total": f"{bucket['total']:,.2f}",
            "currency": bucket["currency"],
        })
    return summary


def manifest_doc(run_id: str) -> dict:
    run = store.get_run(run_id) or {}
    report = reconcile_service.reconcile(run_id)
    doc = manifest.build(run, {
        "rows": {
            "input": int(run.get("rows_in") or 0),
            "billed": len(invoice_rows(run_id)),
            "quarantined": int(run.get("rows_quarantined") or 0),
        },
        "amount": {
            "total": report["total"],
            "conserved": report["conserved"],
        },
        "reconcile": report["verdict"],
        "rate_set_version": store.max_rate_set_version(),
        "params": {"profile": config.PROFILE, "quant": "0.01", "step": "0.5"},
        "export": {"invoice_rows": len(invoice_rows(run_id))},
    })
    return doc


def manifest_json(run_id: str) -> str:
    return json.dumps(manifest_doc(run_id), ensure_ascii=False, indent=2, sort_keys=True, default=str)
