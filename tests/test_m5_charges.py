"""M5 分区附加：首重续重、最低收费、附加费顺序、Decimal 守恒。"""

from __future__ import annotations

from decimal import Decimal

from fixtures.expected import AMOUNT_TOTAL, PARTS, WAYBILLS

from app.modules.m5_charges import addon, money, zone
from app.modules.m5_charges import service as charges


def _lines(run_id: str) -> dict:
    return {row["waybill_no"]: row for row in charges.lines(run_id)}


def test_zone_first_and_step_amounts():
    card = {"first_price": "13.00", "step_price": "2.60", "min_charge": "19.00"}
    assert zone.first_amount(card) == Decimal("13.00")
    assert zone.step_amount(8, card) == Decimal("20.80")
    assert zone.step_amount(0, card) == Decimal("0.00")
    assert zone.zone_amount(8, card) == Decimal("33.80")


def test_min_charge_topup_applied():
    card = {"first_price": "13.00", "step_price": "2.60", "min_charge": "19.00"}
    assert zone.min_topup(Decimal("13.00"), card) == Decimal("6.00")
    assert zone.min_topup(Decimal("33.80"), card) == Decimal("0.00")


def test_wb_1001_matches_hand_calculation(pipeline):
    """TRAP-10：分项用 Decimal，合计必须精确等于 42.67。"""
    line = _lines(pipeline["run_id"])["WB-1001"]
    assert line["base_amount"] == "13.00"
    assert line["step_amount"] == "20.80"
    assert line["remote_amount"] == "0.00"
    assert line["fuel_amount"] == "2.87"
    assert line["insurance_amount"] == "6.00"
    assert line["total_amount"] == "42.67"


def test_wb_1002_min_charge_reaches_floor(pipeline):
    line = _lines(pipeline["run_id"])["WB-1002"]
    assert line["base_amount"] == "19.00"
    assert line["step_amount"] == "0.00"
    assert line["fuel_amount"] == "1.62"
    assert line["total_amount"] == "20.62"
    assert "MIN_CHARGE_APPLIED" in line["codes"]


def test_wb_1006_unit_conversion_with_topup(pipeline):
    line = _lines(pipeline["run_id"])["WB-1006"]
    assert line["base_amount"] == "12.42"
    assert line["step_amount"] == "4.68"
    assert line["insurance_amount"] == "4.50"
    assert line["total_amount"] == "23.05"


def test_every_total_matches_expected(pipeline):
    lines = _lines(pipeline["run_id"])
    for waybill_no, expected in WAYBILLS.items():
        assert lines[waybill_no]["total_amount"] == expected["total"], waybill_no


def test_amount_total_and_parts(pipeline):
    amounts = charges.amounts(pipeline["run_id"])
    assert str(amounts["total"]) == AMOUNT_TOTAL
    for key, expected in PARTS.items():
        assert str(amounts["parts"][key]) == expected, key
    assert amounts["conserved"] is True


def test_parts_sum_equals_total_exactly(pipeline):
    """TRAP-24：分项先量化到分，求和必须一分不差。"""
    amounts = charges.amounts(pipeline["run_id"])
    total = money.total(amounts["parts"].values())
    assert str(total) == AMOUNT_TOTAL
    assert money.conserved(amounts["total"], amounts["parts"].values()) is True
    assert money.delta(amounts["total"], amounts["parts"].values()) == Decimal("0.00")


def test_float_accumulation_would_drift(pipeline):
    """TRAP-10 反例：逐分用 float 累加会漂移，用 Decimal 精确。"""
    naive = 0.0
    for _ in range(100):
        naive += 0.01
    assert naive != 1.0

    exact = Decimal("0")
    for _ in range(100):
        exact += Decimal("0.01")
    assert exact == Decimal("1.00")

    rows = charges.lines(pipeline["run_id"])
    assert money.total([Decimal(row["total_amount"]) for row in rows]) == Decimal(AMOUNT_TOTAL)


def test_fuel_only_on_base_and_step():
    card = {"fuel_pct": "0.085", "remote_fee": "6.50", "insurance_pct": "0.0040"}
    assert addon.fuel_amount(Decimal("20.00"), Decimal("610.60"), card) == Decimal("53.60")
    assert addon.remote_amount(card) == Decimal("6.50")
    assert addon.insurance_amount(Decimal("800.00"), card) == Decimal("3.20")


def test_remote_only_for_remote_zone(pipeline):
    lines = _lines(pipeline["run_id"])
    assert lines["WB-1005"]["remote_amount"] == "6.50"
    assert lines["WB-1015"]["remote_amount"] == "10.00"
    assert lines["WB-1001"]["remote_amount"] == "0.00"


def test_addon_order_is_declared():
    assert addon.order() == ("base", "step", "remote", "fuel", "insurance")
