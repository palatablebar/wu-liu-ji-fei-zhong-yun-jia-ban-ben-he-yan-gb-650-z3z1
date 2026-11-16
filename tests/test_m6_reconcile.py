"""M6 账单对账：四账相等、分项、差异归因。"""

from __future__ import annotations

from decimal import Decimal

from fixtures.expected import AMOUNT_TOTAL, PARTS, ROWS_IN, ROWS_OK, ROWS_QUARANTINED, VOLUMETRIC_HITS

from app.modules.m6_reconcile import compare, explain, totals
from app.modules.m6_reconcile import service as reconcile


def _accounts(run_id: str) -> dict:
    report = reconcile.reconcile(run_id)
    return {account["key"]: account for account in report["accounts"]}


def test_four_accounts_all_balanced(pipeline):
    report = reconcile.reconcile(pipeline["run_id"])
    assert len(report["accounts"]) == 4
    assert report["verdict"]["balanced"] is True
    assert report["verdict"]["broken"] == []


def test_row_account_conserves(pipeline):
    account = _accounts(pipeline["run_id"])["rows"]
    assert account["left_value"] == ROWS_IN
    parts = {part["label"]: part["value"] for part in account["parts"]}
    assert parts["计费"] == ROWS_OK
    assert parts["隔离"] == ROWS_QUARANTINED
    assert account["balanced"] is True


def test_amount_account_parts(pipeline):
    account = _accounts(pipeline["run_id"])["amount"]
    assert str(account["left_value"]) == AMOUNT_TOTAL
    labels = {"基础运费": "base", "续重运费": "step", "偏远附加": "remote",
              "燃油附加": "fuel", "保价费": "insurance"}
    got = {labels[part["label"]]: str(part["value"]) for part in account["parts"]}
    assert got == PARTS
    assert account["balanced"] is True


def test_version_account_single_pick(pipeline):
    account = _accounts(pipeline["run_id"])["version"]
    assert account["left_value"] == ROWS_OK
    assert account["parts"] == [{"label": "单选命中", "value": ROWS_OK}]
    assert account["balanced"] is True


def test_weight_account_splits_by_source(pipeline):
    account = _accounts(pipeline["run_id"])["weight"]
    parts = {part["label"]: part["value"] for part in account["parts"]}
    assert parts["体积重择用"] == VOLUMETRIC_HITS
    assert parts["实重择用"] == ROWS_OK - VOLUMETRIC_HITS
    assert account["balanced"] is True


def test_report_total_matches_run(pipeline):
    report = reconcile.reconcile(pipeline["run_id"])
    assert report["total"] == AMOUNT_TOTAL
    assert report["conserved"] is True
    assert report["rows_in"] == ROWS_IN
    assert report["amount_total"] == AMOUNT_TOTAL


def test_balanced_account_note(pipeline):
    for account in reconcile.reconcile(pipeline["run_id"])["accounts"]:
        assert account["note"] == explain.BALANCED


def test_unbalanced_account_gets_template():
    fake = {
        "key": "amount",
        "balanced": False,
        "delta": Decimal("-0.01"),
        "left_value": Decimal("1.00"),
        "parts": [],
        "right_value": Decimal("1.01"),
    }
    note = explain.note(fake)
    assert "-0.01" in note
    assert note == explain.AMOUNT_TEMPLATE.format(delta=Decimal("-0.01"))
    verdict = explain.verdict([fake])
    assert verdict["balanced"] is False
    assert verdict["broken"] == ["amount"]


def test_totals_helpers_agree(pipeline):
    rows = __import__("app.store", fromlist=["store"]).charge_lines(pipeline["run_id"])
    assert totals.conserved(rows) is True
    assert str(totals.grand_total(rows)) == AMOUNT_TOTAL
    assert totals.part_labels()["base"] == "基础运费"
    assert totals.step_total(rows) == 11
