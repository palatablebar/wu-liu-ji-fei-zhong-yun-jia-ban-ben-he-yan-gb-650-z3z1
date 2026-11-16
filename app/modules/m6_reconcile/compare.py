"""四账：运单行账、金额账、版本账、计费重账。每账给出左右两侧与差额。"""

from __future__ import annotations

from decimal import Decimal

from app import store
from app.modules.m4_weights import billable
from app.modules.m6_reconcile import totals


def _account(key: str, title: str, left_label: str, left_value, parts: list[dict],
             unit: str) -> dict:
    right = Decimal("0") if unit == "元" else 0
    for part in parts:
        right = right + part["value"]
    delta = left_value - right
    return {
        "key": key,
        "title": title,
        "left_label": left_label,
        "left_value": left_value,
        "parts": parts,
        "right_value": right,
        "delta": delta,
        "balanced": delta == 0,
        "unit": unit,
    }


def row_account(run: dict, quarantine_rows: list[dict], weight_rows: list[dict]) -> dict:
    quarantined = len({row["line_no"] for row in quarantine_rows})
    billed = sum(1 for row in weight_rows if row["source"] != billable.UNBILLED)
    unbilled = sum(1 for row in weight_rows if row["source"] == billable.UNBILLED)
    parts = [
        {"label": "计费", "value": billed},
        {"label": "隔离", "value": quarantined},
    ]
    if unbilled:
        parts.append({"label": "未计费", "value": unbilled})
    return _account(
        "rows",
        "运单行账",
        "采信记录",
        int(run.get("rows_in") or 0),
        parts,
        "行",
    )


def amount_account(charge_rows: list[dict]) -> dict:
    parts_map = totals.parts_of(charge_rows)
    labels = totals.part_labels()
    parts = [
        {"label": labels[key], "value": value}
        for key, value in parts_map.items()
    ]
    return _account(
        "amount",
        "金额账",
        "应收合计",
        totals.grand_total(charge_rows),
        parts,
        "元",
    )


def version_account(run: dict, weight_rows: list[dict]) -> dict:
    total = int(run.get("rows_ok") or 0)
    hit = sum(1 for row in weight_rows if row["version_id"])
    miss = sum(1 for row in weight_rows if not row["version_id"])
    parts = [{"label": "单选命中", "value": hit}]
    if miss:
        parts.append({"label": "无命中或重叠", "value": miss})
    return _account("version", "版本账", "可计费运单", total, parts, "行")


def weight_account(weight_rows: list[dict]) -> dict:
    actual = sum(1 for row in weight_rows if row["source"] in (billable.ACTUAL, billable.TIE))
    volumetric = sum(1 for row in weight_rows if row["source"] == billable.VOLUMETRIC)
    billed = actual + volumetric
    parts = [
        {"label": "实重择用", "value": actual},
        {"label": "体积重择用", "value": volumetric},
    ]
    return _account("weight", "计费重账", "计费行数", billed, parts, "行")


def accounts(run: dict, quarantine_rows: list[dict], weight_rows: list[dict],
             charge_rows: list[dict]) -> list[dict]:
    return [
        row_account(run, quarantine_rows, weight_rows),
        amount_account(charge_rows),
        version_account(run, weight_rows),
        weight_account(weight_rows),
    ]


def run_of(run_id: str) -> dict:
    return store.get_run(run_id) or {}
