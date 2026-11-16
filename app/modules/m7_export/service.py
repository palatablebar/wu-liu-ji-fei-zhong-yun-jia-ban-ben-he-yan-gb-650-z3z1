"""M7 编排：导出内容的组装与统计。"""

from __future__ import annotations

from app import store
from app.modules.m7_export import csv_out, invoice_out


def invoice_csv(run_id: str) -> str:
    return invoice_out.invoice_csv(run_id)


def evidence_csv(run_id: str) -> str:
    return csv_out.csv_text(run_id)


def manifest_json(run_id: str) -> str:
    return invoice_out.manifest_json(run_id)


def overview(run_id: str) -> dict:
    invoices = invoice_out.invoice_rows(run_id)
    evidence = csv_out.rows(run_id)
    doc = invoice_out.manifest_doc(run_id)
    return {
        "run_id": run_id,
        "invoice_rows": len(invoices),
        "evidence_rows": len(evidence),
        "carriers": invoice_out.carrier_summary(run_id),
        "manifest": doc,
        "input_sha256": doc.get("input_sha256", ""),
        "amount_total": doc.get("amount_total", "0.00"),
        "rows": doc.get("rows", {}),
    }
