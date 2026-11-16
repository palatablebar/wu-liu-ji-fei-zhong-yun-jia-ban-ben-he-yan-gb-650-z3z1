"""返利分摊导出：月度汇总行 + 逐票分摊行，供月账复核与归档。"""

from __future__ import annotations

import csv
import io

from app import store

MONTH_HEADER = [
    "row_kind", "carrier", "month", "waybill_no", "base_amount", "weight_share",
    "rebate_amount", "rebate_pct", "status", "codes",
]


def rows(run_id: str) -> list[dict]:
    out: list[dict] = []
    for month in store.rebate_months(run_id):
        out.append({
            "row_kind": "month",
            "carrier": month["carrier"],
            "month": month["month"],
            "waybill_no": "",
            "base_amount": month["base_total"],
            "weight_share": "",
            "rebate_amount": month["rebate_total"],
            "rebate_pct": month["rebate_pct"],
            "status": month["status"],
            "codes": "",
        })
    for line in store.rebate_lines(run_id):
        out.append({
            "row_kind": "allocation",
            "carrier": line["carrier"],
            "month": line["month"],
            "waybill_no": line["waybill_no"],
            "base_amount": line["base_amount"],
            "weight_share": line["weight_share"],
            "rebate_amount": line["rebate_amount"],
            "rebate_pct": "",
            "status": "",
            "codes": line["codes"],
        })
    return out


def csv_text(run_id: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MONTH_HEADER)
    for row in rows(run_id):
        writer.writerow([row[key] for key in MONTH_HEADER])
    return buffer.getvalue()
