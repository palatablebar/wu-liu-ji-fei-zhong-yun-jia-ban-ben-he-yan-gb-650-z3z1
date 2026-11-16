"""M6 编排：取四份账的输入，算账并附带归因。"""

from __future__ import annotations

from app import store
from app.modules.m6_reconcile import compare, explain, totals


def reconcile(run_id: str) -> dict:
    run = store.get_run(run_id) or {}
    quarantine_rows = store.quarantine(run_id)
    weight_rows = store.weight_lines(run_id)
    charge_rows = store.charge_lines(run_id)
    accounts = compare.accounts(run, quarantine_rows, weight_rows, charge_rows)
    explain.annotated(accounts)
    return {
        "run_id": run_id,
        "accounts": accounts,
        "verdict": explain.verdict(accounts),
        "total": str(totals.grand_total(charge_rows)),
        "conserved": totals.conserved(charge_rows),
        "rows_in": int(run.get("rows_in") or 0),
        "rows_ok": int(run.get("rows_ok") or 0),
        "amount_total": str(run.get("amount_total") or "0.00"),
    }
